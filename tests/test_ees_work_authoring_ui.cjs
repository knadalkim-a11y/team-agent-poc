/* Definition editor contracts with a synthetic DOM. Native product verification
 * is separate: these do not claim browser layout or operational EES success. */
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),crypto=require('node:crypto'),path=require('node:path');
const {renderer,run}=require('./ees_workspace_ui_fixture.cjs');
// A captured main source can prove new requirements fail before parallel product edits.
const source=fs.readFileSync(process.env.EES_AUTHORING_TEST_SOURCE || path.join(__dirname,'../branding/ees/ui/ees-work-designer.js'),'utf8');
const copy=value=>JSON.parse(JSON.stringify(value));
const toolExamples=[
 {id:'jira-query',name:'Jira 조회',description:'배포 전에 CR 승인 상태를 확인합니다.',kind:'read',match:{function:'jira_search_crs'}},
 {id:'service-status',name:'서비스 상태 조회',description:'EMS 서비스의 현재 상태를 확인합니다.',kind:'read',match:{function:'service_status'},requires_read_allowlist:true},
 {id:'collection-queue',name:'수집 대기열 조회',description:'EMS 수집 대기열을 확인합니다.',kind:'read',match:{function:'collection_queue'},requires_read_allowlist:true},
 {id:'restart-service',name:'서비스 재시작 요청',description:'EES에 서비스 재시작을 부탁합니다.',kind:'request',match:{tool_id:'ops',function:'restart_service'}},
];
const procedureExamples=[
 {id:'delivery_review',name:'배포 산출물 점검',description:'배포 자료를 순서대로 점검합니다.',category:'ops',mode:'periodic',execution_scope:null,stage_count:4,job_count:9,stages:[{name:'대상 확정',job_count:2},{name:'1차 점검',job_count:3},{name:'보완·재점검',job_count:2},{name:'조건부 승인 후속',job_count:2}],schedule_suggestion:'격주 화요일'},
 {id:'factory_rollout',name:'신규 공장 횡전개',description:'새 공장에 시스템을 설치합니다.',category:'setup',mode:'on_demand',execution_scope:'factory',stage_count:4,job_count:6,stages:[{name:'사전준비',job_count:1},{name:'AP·DB 인프라 준비',job_count:2},{name:'시스템 설치',job_count:1},{name:'시스템 간 인터페이스 확인',job_count:2}],schedule_suggestion:''},
 {id:'daily_check',name:'일일 시스템 점검',description:'매일 시스템 상태를 확인합니다.',category:'ops',mode:'periodic',execution_scope:null,stage_count:1,job_count:1,stages:[{name:'시스템 점검',job_count:1}],schedule_suggestion:'매일'},
];
const nativeFunction=(tool_id,name,kind='read',functionName='read')=>({name:tool_id==='jira'?'연결된 Jira':'연결된 '+tool_id,function_name:name,kind,reference:{tool_id,function:functionName,content_hash:'current'},schema:{type:'object',properties:{target:{type:'string'}}}});
const flush=async()=>{for(let i=0;i<8;i++)await new Promise(r=>setImmediate(r));};
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
const decode=value=>String(value).replaceAll('&quot;','"').replaceAll('&#39;',"'").replaceAll('&lt;','<').replaceAll('&gt;','>').replaceAll('&amp;','&');
const attr=(text,name)=>decode(text.match(new RegExp('(?:^|\\s)'+name+'="([^"]*)"'))?.[1] || '');
function controlAttributes(text){const attributes=Object.fromEntries([...text.matchAll(/([\w-]+)="([^"]*)"/g)].map(([,key,value])=>[key,decode(value)]));for(const key of ['disabled','readonly','required','checked','data-dialog-confirm','data-dialog-cancel'])if(new RegExp('\\b'+key+'\\b').test(text))attributes[key]='';return attributes;}
function controls(html){
 const result=[];
 for(const m of html.matchAll(/<input\b([^>]*)>/g))result.push({offset:m.index,name:attr(m[1],'name'),id:attr(m[1],'id'),value:attr(m[1],'value'),type:attr(m[1],'type'),checked:/\bchecked\b/.test(m[1]),disabled:/\bdisabled\b/.test(m[1]),attributes:controlAttributes(m[1])});
 for(const m of html.matchAll(/<textarea\b([^>]*)>([\s\S]*?)<\/textarea>/g))result.push({offset:m.index,name:attr(m[1],'name'),id:attr(m[1],'id'),value:decode(m[2]),type:'textarea',disabled:/\bdisabled\b/.test(m[1]),attributes:controlAttributes(m[1])});
 for(const m of html.matchAll(/<select\b([^>]*)>([\s\S]*?)<\/select>/g)){const options=[...m[2].matchAll(/<option\b([^>]*)>([^<]*)<\/option>/g)],o=options.find(o=>/\bselected\b/.test(o[1])) || options[0];result.push({offset:m.index,name:attr(m[1],'name'),id:attr(m[1],'id'),value:o?attr(o[1],'value'):'',type:'select',disabled:/\bdisabled\b/.test(m[1]),attributes:controlAttributes(m[1])});}
 return result;
}
function ancestorMap(html){
 const parents=new Map(),stack=[],voids=new Set(['input','img','br','hr','meta','link']);
 for(const match of html.matchAll(/<(\/?)([a-z][\w-]*)\b([^>]*)>/gi)){
  const [,closing,tag,raw]=match;if(closing){for(let i=stack.length-1;i>=0;i--)if(stack[i].tagName===tag){stack.length=i;break;}continue;}
  const parent=stack.at(-1)||null,node={offset:match.index,tagName:tag,id:attr(raw,'id'),className:attr(raw,'class'),attributes:controlAttributes(raw),parentElement:parent};parents.set(match.index,parent);if(!voids.has(tag))stack.push(node);
 }
 return parents;
}

function definition(id='w'){return {id,name:'절차 '+id,system_id:'EMS',category:'ops',mode:'on_demand',nodes:{p:{id:'p',type:'p',parent:null,children:['t'],deps:[],name:'절차'},t:{id:'t',type:'t',parent:'p',children:['j'],deps:[],name:'단계'},j:{id:'j',type:'j',parent:'t',children:[],deps:[],name:'확인 작업',instructions:'원래 안내',mode:'human',inputs:[],result_block:'human_confirm',human_confirmation:true}}};}
function stagedDefinition(count=3,jobsPerStage=2){const value=definition();value.nodes={p:{id:'p',type:'p',parent:null,children:[],deps:[],name:'절차'}};for(let i=0;i<count;i++){const id='t'+i;value.nodes.p.children.push(id);value.nodes[id]={id,type:'t',parent:'p',children:[],deps:[],name:'단계 '+(i+1),description:'첫 줄\n둘째 줄'};for(let j=0;j<jobsPerStage;j++){const job='j'+i+'-'+j;value.nodes[id].children.push(job);value.nodes[job]={...copy(definition().nodes.j),id:job,parent:id,name:'작업 '+(i+1)+'-'+(j+1)};}}return value;}
function installDefinition(h,value){h.workflows.get('w').draft=copy(value);h.state.workflow=h.workflows.get('w');h.render();}
const stageButton=(h,id)=>h.buttons.find(button=>button.dataset.authorAction==='stage_toggle'&&button.dataset.id===id);
const actionButton=(h,action,id)=>h.buttons.find(button=>button.dataset.authorAction===action&&(id===undefined||button.dataset.id===id));
const staleInlineMessage='저장된 초안이 바뀌었습니다. 입력한 내용은 보존했습니다. 취소한 뒤 최신 내용을 확인하고 다시 편집해 주세요.';
const deletedInlineMessage='편집하던 단계가 최신 초안에서 삭제되었습니다. 입력한 내용은 보존했습니다. 필요하면 복사한 뒤 취소해 주세요.';
const inlineMarkup=h=>h.markup.match(/<form\b[^>]*id="ew-stage-editor"[^>]*>([\s\S]*?)<\/form>/)?.[1] || '';
function assertUnavailableInline(h,message){
 const html=inlineMarkup(h);assert.ok(html,'the buffered inline form remains visible');
 const first=html.match(/^<p\b([^>]*)>([\s\S]*?)<\/p>/);assert.ok(first,'the first form element is the concurrent-edit notice');assert.equal(attr(first[1],'class'),'ew-inline-error');assert.equal(attr(first[1],'role'),'alert');assert.equal(decode(first[2]),message);
 assert.equal([...html.matchAll(/class="ew-inline-error"/g)].length,1,'show exactly one form notice');
 assert.doesNotMatch(html,/<input\b[^>]*name="name"[^>]*(?:aria-invalid|aria-describedby)/);assert.doesNotMatch(html,/id="ew-stage-name-error"/);assert.doesNotMatch(html,/먼저 적용하거나/);
 assert.deepEqual([...html.matchAll(/data-author-action="(inline_[^"]+)"/g)].map(match=>match[1]),['inline_cancel']);
 assert.doesNotMatch(html,/적용: 저장 전 초안에 반영|맨 아래에 추가하고 바로 펼칩니다|추가하면 이 단계 맨 아래에 생기고 작업 상세가 열립니다/);
}
async function submitInline(h){const result=h.designer.handleEvent({type:'submit',target:h.forms['ew-stage-editor']});await flush();assert.deepEqual(copy(result),{handled:true,preventDefault:true});}
async function beginInline(h,kind){h.click(kind==='stage'?'stage_edit':kind,kind==='stage'?{id:'t0'}:kind==='add_job'?{parent:'t0'}:{});await flush();}

function footerNodes(html){const result={};for(const m of html.matchAll(/<(small|p)\b([^>]*)>([\s\S]*?)<\/\1>/g)){const attributes=m[2],id=attr(attributes,'id'),summary=attributes.match(/data-(procedure|tool)-summary/)?.[0],node={textContent:decode(m[3])};if(id)result['#'+id]=node;if(summary)result['['+summary+']']=node;}return result;}
function harness({cryptoProvider=crypto,proposalChangesObserver=null}={}){const h={startContexts:[],writes:[],operations:[],reads:[],dialogs:[],proposals:[],markup:'',forms:{},buttons:[],fields:[]};h.workflows=new Map(['w','q'].map(id=>[id,{id,name:'절차 '+id,system_id:'EMS',can_manage:true,revision:1,published_version:null,draft:definition(id),validation:{revision:1,errors:[],warnings:[]},versions:[]}]));h.state={capabilities:{actor_id:'a',can_author:true,managed_systems:['EMS']},workflows:[...h.workflows.values()],workflow:h.workflows.get('w'),factories:[{id:'f',name:'공장'}],tools:[],native_functions:[],tool_examples:copy(toolExamples),procedure_examples:copy(procedureExamples)};h.selection={system_id:'EMS',workflow_id:'w',mode:'author',chat_id:'private-chat'};
 const noop=()=>{};let dialog=null;
 const matches=(node,selector)=>{
  if(selector.includes(','))return selector.split(',').some(part=>matches(node,part.trim()));
  if(selector.startsWith('#'))return node.id===selector.slice(1);
  if(selector.startsWith('.'))return (node.className || '').split(' ').includes(selector.slice(1));
  const attrs=[...selector.matchAll(/\[([^=\]]+)(?:=["']?([^"'\]]*)["']?)?\]/g)];
  return attrs.length>0&&attrs.every(([,name,value])=>value===undefined?Object.hasOwn(node.attributes || {},name):String(node.attributes?.[name] ?? '')===value);
 };
 const decorate=(node,attributes={})=>{
  let disabled=Boolean(node.disabled);Object.defineProperty(node,'disabled',{get:()=>disabled,set:value=>{disabled=Boolean(value);},enumerable:true,configurable:true});node.attributes=attributes;node.dataset ||= {};for(const [key,value] of Object.entries(attributes))if(key.startsWith('data-'))node.dataset[key.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=value;node.isConnected=true;node.focus=()=>{h.document.activeElement=node;};node.setSelectionRange=(start,end)=>{node.selectionStart=start;node.selectionEnd=end;};
  node.scrollIntoView=options=>{(h.scrollRequests ||= []).push({node,options});};node.getAttribute=name=>Object.hasOwn(node.attributes,name)?node.attributes[name]:null;node.setAttribute=(name,value)=>{node.attributes[name]=String(value);};
  node.closest=selector=>{if(selector==='#ees-work-designer')return host;if(selector==='#'+node.formId)return h.forms[node.formId];for(let current=node;current;current=current.parentElement)if(matches(current,selector))return current;return null;};
  return node;
 };
 const host={isConnected:true,contains:node=>Boolean(node&&(h.fields.includes(node)||h.buttons.includes(node)||(h.summaries||[]).includes(node)||Object.values(h.forms).includes(node))),querySelector(selector){
  if(selector.endsWith('>summary'))return (h.summaries||[]).find(node=>matches(node.parentElement,selector.slice(0,-8)))||null;
  if(selector==='footer')return h.footer;if(h.footerNodes?.[selector])return h.footerNodes[selector];if(selector==='.ew-author-ai')return h.composer;if(selector==='.ew-author-scroll')return h.scroll;if(selector==='[data-author-status]')return h.status;if(selector==='.ew-schedule-preview')return h.schedulePreview;
  if(selector.includes(','))return selector.split(',').map(part=>host.querySelector(part)).find(Boolean) || null;
  const formError=selector.match(/^#([^ ]+) \.ew-inline-error$/);if(formError)return h.forms[formError[1]]?.inlineError || null;
  const namedFormControl=selector.match(/^#([^ ]+) (\[name=[^\]]+\])$/);if(namedFormControl)return h.forms[namedFormControl[1]]?.controls.find(field=>matches(field,namedFormControl[2])) || null;
  const formControl=selector.match(/^#([^ ]+) (input|select|textarea)/);if(formControl)return h.forms[formControl[1]]?.controls.find(field=>field.type!=='hidden') || null;
  if(selector.startsWith('#')&&h.forms[selector.slice(1)])return h.forms[selector.slice(1)];
  return [...h.fields,...h.buttons,...(h.details || [])].find(node=>matches(node,selector)) || null;
 },querySelectorAll(selector){
  if(selector==='[data-mutation]')return h.buttons.filter(b=>b.mutation);if(selector==='input,select,textarea')return h.fields;
  return [...h.buttons,...h.fields].filter(node=>matches(node,selector));
 },set innerHTML(html){
  const ownedFocus=host.contains(h.document?.activeElement);for(const node of [...h.fields,...h.buttons])node.isConnected=false;if(ownedFocus)h.document.activeElement=null;
  h.markup=html;const parents=ancestorMap(html);h.status={textContent:decode(html.match(/data-author-status[^>]*>([^<]*)/)?.[1] || '')};
  const footer=html.match(/<footer(?:\s[^>]*)?>([\s\S]*?)<\/footer>/)?.[1];h.footerNodes=footerNodes(footer || '');h.footer=footer===undefined?null:{};
  if(h.footer)Object.defineProperty(h.footer,'innerHTML',{get:()=>footer,set:value=>{h.footerReplacements=(h.footerReplacements || 0)+1;h.footerNodes=footerNodes(value);h.buttons=h.buttons.map(button=>['procedure_create','procedure_cancel','tool_save','tool_review','tool_approve','tool_reject'].includes(button.dataset.authorAction)?{...button}:button);}});
  h.summaries=[...html.matchAll(/<summary\b([^>]*)>/g)].map(m=>decorate({tagName:'SUMMARY',parentElement:parents.get(m.index)},controlAttributes(m[1])));
  h.details=[...html.matchAll(/<details\b([^>]*)>/g)].map(m=>decorate({className:attr(m[1],'class'),open:/\bopen\b/.test(m[1])},{class:attr(m[1],'class')}));h.composer=h.details.find(node=>node.className==='ew-author-ai') || null;
  h.scroll={scrollTop:0,querySelectorAll:selector=>h.details.filter(node=>![...selector.matchAll(/:not\(\.([^)]*)\)/g)].some(([,name])=>(node.className || '').split(' ').includes(name)))};h.fields=controls(html).map(field=>decorate({...field,parentElement:parents.get(field.offset)},field.attributes));h.forms={};
  const formMatches=[...html.matchAll(/<form\b([^>]*)>([\s\S]*?)<\/form>/g)];
  for(const m of formMatches){
   const id=attr(m[1],'id'),c=controls(m[2]).map(field=>decorate({...field,offset:m.index+m[0].indexOf('>')+1+field.offset,formId:id,parentElement:parents.get(m.index+m[0].indexOf('>')+1+field.offset)},field.attributes));
   h.forms[id]=decorate({id,controls:c});if(m[2].includes('class="ew-inline-error"'))h.forms[id].inlineError=decorate({className:'ew-inline-error',formId:id});
   for(const field of c){const old=h.fields.findIndex(f=>f.offset===field.offset);if(old>=0)h.fields[old]=field;}
  }
  h.buttons=[...html.matchAll(/<button\b([^>]*)>/g)].map(m=>{const attributes=Object.fromEntries([...m[1].matchAll(/([\w-]+)="([^"]*)"/g)].map(([,k,v])=>[k,decode(v)]));const formMatch=formMatches.find(form=>m.index>form.index&&m.index<form.index+form[0].length);return decorate({tagName:'BUTTON',parentElement:parents.get(m.index),formId:formMatch?attr(formMatch[1],'id'):'',id:attr(m[1],'id'),className:attr(m[1],'class'),dataset:{authorAction:attr(m[1],'data-author-action'),id:attr(m[1],'data-id'),tab:attr(m[1],'data-tab'),parent:attr(m[1],'data-parent')},disabled:/\bdisabled\b/.test(m[1]),mutation:/data-mutation/.test(m[1])},attributes);});
  const previewMatch=html.match(/<section class="ew-schedule-preview"[^>]*>([\s\S]*?)<\/section>/);h.schedulePreview=previewMatch?{}:null;
  if(h.schedulePreview){let value=previewMatch[1];Object.defineProperty(h.schedulePreview,'innerHTML',{get:()=>value,set:next=>{
   value=next;h.markup=h.markup.replace(/(<section class="ew-schedule-preview"[^>]*>)[\s\S]*?(<\/section>)/,(_,start,end)=>start+next+end);
   for(const button of h.buttons.filter(b=>b.dataset.authorAction==='schedule_preview'))button.isConnected=false;
   h.buttons=h.buttons.filter(b=>b.dataset.authorAction!=='schedule_preview');for(const m of next.matchAll(/<button\b([^>]*)>/g)){const attributes=controlAttributes(m[1]);h.buttons.push(decorate({tagName:'BUTTON',className:attr(m[1],'class'),disabled:/\bdisabled\b/.test(m[1]),mutation:/data-mutation/.test(m[1])},attributes));}
  }});}
 },get innerHTML(){return h.markup;}};
 const callbacks={startContextChanged:value=>h.startContexts.push(value),read:async query=>{h.reads.push(copy(query));if(h.readOverride)return h.readOverride(query);return {workflow:copy(h.workflows.get(query.workflow_id)),capabilities:copy(h.state.capabilities)};},command:async body=>{h.writes.push(copy(body));if(h.writeOverride)return h.writeOverride(body);if(body.action==='create_workflow'){const id='created-'+h.writes.length,draft=definition(id);draft.name=body.name;draft.system_id=body.system_id;draft.nodes={p:{id:'p',type:'p',name:body.name,parent:null,children:[]}};const record={id,name:body.name,system_id:body.system_id,can_manage:true,revision:1,published_version:null,draft,validation:null,versions:[]};h.workflows.set(id,record);h.state.workflows=[...h.workflows.values()];return {ok:true,workflow_id:id,revision:1,workflow:copy(record)};}const record=h.workflows.get(body.workflow_id);if(body.action==='save_draft'){record.draft=copy(body.definition);record.revision++;record.validation=null;return {ok:true,revision:record.revision};}if(body.action==='validate_workflow'){record.validation={revision:record.revision,errors:[],warnings:[]};return {ok:true,revision:record.revision,validation:copy(record.validation)};}if(body.action==='publish_workflow'){record.revision++;record.published_version=(record.published_version || 0)+1;record.validation=null;return {ok:true,revision:record.revision,version:record.published_version};}return {ok:true};},operationsCommand:async body=>{h.operations.push(copy(body));if(h.operationOverride)return h.operationOverride(body);return {ok:true,tool:{...copy(body.tool || h.state.tools.find(t=>t.id===body.tool_contract_id)),id:'tool',revision:2,state:body.action==='tool_submit'?'review_requested':'draft'}};},models:async()=>{h.modelReads=(h.modelReads || 0)+1;return h.modelsOverride?h.modelsOverride():{models:[{id:'m',name:'Native 모델'}],preferred:['m']};},propose:async body=>{h.proposals.push(body);return h.proposeOverride?h.proposeOverride(body):{workflow_id:body.workflow_id,base_revision:body.expected_revision,context_id:body.context_id,definition:{...copy(body.definition),name:'AI 제안'},summary:'초안 제안'};},openWorkflow:async id=>{h.selection.workflow_id=id;h.state.workflow=h.workflows.get(id) || null;h.designer.render({state:h.state,selection:h.selection,host});},changed:async()=>{h.state.workflow=h.workflows.get(h.selection.workflow_id) || null;h.designer.render({state:h.state,selection:h.selection,host});}};
 // Model only the existing dialog host lifecycle. Candidate/value listeners below
 // are the product handlers; the fixture does not apply drafts on their behalf.
 function toolDialog(options){
  let markup=options.html+'<footer><button data-dialog-cancel>취소</button><button data-dialog-confirm>적용</button></footer>',resolve;
  const listeners={},surface={id:'ees-work-dialog',closest:()=>null,classList:{add(){},remove(){}},addEventListener(type,fn){(listeners[type] ||= []).push(fn);},contains(target){return h.modalNodes.includes(target);}};
  const bounds=node=>{const start=markup.indexOf('>',node.offset)+1;let depth=1,end=start;const re=/<(\/?)([a-z][\w-]*)\b[^>]*>/gi;re.lastIndex=start;for(let m;(m=re.exec(markup));){if(m[2].toLowerCase()!==node.tagName.toLowerCase())continue;depth+=m[1]?-1:1;if(!depth){end=m.index;break;}}return [start,end];};
  const select=(selector,within)=>{
   if(selector.includes(','))return [...new Set(selector.split(',').flatMap(s=>select(s.trim(),within)))];
   let query=selector.trim();const lastSpace=query.lastIndexOf(' ');if(lastSpace>=0)query=query.slice(lastSpace+1);
   return h.modalNodes.filter(node=>{
    if(within&&!function(){for(let p=node.parentElement;p;p=p.parentElement)if(p.offset===within.offset)return true;return false;}())return false;
    if(query.includes(':not([disabled])')&&node.disabled)return false;
    if(query.includes(':checked')&&!node.checked)return false;
    const clean=query.replace(/:not\([^)]*\)|:checked|:first-child/g,''),tag=clean.match(/^[a-z]+/i)?.[0];
    if(tag&&node.tagName.toLowerCase()!==tag.toLowerCase())return false;
    const suffix=tag?clean.slice(tag.length):clean;return !suffix||matches(node,suffix);
   });
  };
  const parse=()=>{const parents=ancestorMap(markup),fields=controls(markup);h.modalNodes=[...markup.matchAll(/<(?!\/)([a-z][\w-]*)\b([^>]*)>/gi)].map(m=>{
    const attributes=controlAttributes(m[2]),field=fields.find(f=>f.offset===m.index),node=decorate({offset:m.index,tagName:m[1],id:attr(m[2],'id'),className:attr(m[2],'class'),parentElement:parents.get(m.index),...field},attributes);
    node.addEventListener=(type,fn)=>{(node.listeners ||= {})[type] ||= [];node.listeners[type].push(fn);};node.classList={add(){},remove(){},toggle(){}};node.removeAttribute=name=>{delete node.attributes[name];};node.hasAttribute=name=>Object.hasOwn(node.attributes,name);node.querySelector=s=>select(s,node)[0]||null;node.querySelectorAll=s=>select(s,node);node.checkValidity=()=>true;node.reportValidity=noop;
    const end=markup.indexOf('<',markup.indexOf('>',m.index)+1);node.textContent=decode(markup.slice(markup.indexOf('>',m.index)+1,end));
    Object.defineProperty(node,'innerHTML',{get(){const [a,b]=bounds(node);return markup.slice(a,b);},set(value){const [a,b]=bounds(node);markup=markup.slice(0,a)+value+markup.slice(b);parse();}});
    return node;
   });h.modalMarkup=markup;};
  surface.querySelector=s=>select(s)[0]||null;surface.querySelectorAll=s=>select(s);dialog=surface;parse();h.modal=surface;
  h.modalEvent=(type,target,extra={})=>{let prevented=false;const event={type,target,...extra,preventDefault(){prevented=true;},stopPropagation(){},stopImmediatePropagation(){prevented=true;}};for(const fn of listeners[type]||[])fn(event);for(const fn of target?.listeners?.[type]||[])fn(event);return !prevented;};
  h.modalField=(attribute,id,value,type='input')=>{const target=surface.querySelector('['+attribute+(id===undefined?'':'="'+id+'"')+']');assert.ok(target,'modal field '+attribute+' '+id);if(target.type==='checkbox')target.checked=value;else target.value=value;target.focus();h.modalEvent(type,target);};
  h.modalCandidate=value=>{const target=surface.querySelector('[data-job-tool-candidate="'+value+'"]');assert.ok(target,'candidate '+value);target.focus();h.modalEvent('click',target);};
  h.modalClose=async(kind='cancel',{immediate=false}={})=>{const finish=accepted=>{if(immediate)options.restoreFocus?.();resolve(accepted);};if(kind==='apply'){const button=surface.querySelector('[data-dialog-confirm]');if(button.disabled)return false;if(!h.modalEvent('click',button))return false;finish(true);}else {h.modalEvent(kind==='escape'?'keydown':'click',kind==='escape'?surface:surface.querySelector('[data-dialog-cancel]'),{key:kind==='escape'?'Escape':undefined});finish(false);}await flush();if(!immediate)options.restoreFocus?.();h.modal=null;return true;};
  return new Promise(done=>{resolve=done;});
 }
 const workUI={showHelp:options=>{(h.helpCalls ||= []).push(options);},newId:run(renderer({crypto:cryptoProvider}),'workUI.newId'),esc:value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;'),icon:id=>'<img src="/_ees13/v4/'+id+'.svg" alt="">',$:selector=>selector==='#ees-work-dialog'?dialog:null,dialog:options=>{h.dialogHistory ||= [];h.dialogHistory.push(options);if(options.html?.includes('ew-workflow-tool-setup'))return toolDialog(options);const answer=h.dialogs.shift();assert.notEqual(answer,undefined,'dialog answer is explicit');const listeners={};dialog={addEventListener:(event,cb)=>{(listeners[event] ||= []).push(cb);},querySelectorAll:()=>Object.entries(answer || {}).map(([name,value])=>({name,value,type:typeof value==='boolean'?'checkbox':'text',checked:!!value}))};return Promise.resolve().then(async()=>{await h.dialogHook?.();for(const listener of listeners.click || [])listener({target:{closest:selector=>selector==='[data-dialog-confirm]'?true:null},preventDefault:noop,stopPropagation:noop});return answer!==null;});}};
 const FormData=class{constructor(form){this.data=form.controls.filter(c=>c.name&&!c.disabled&&(!['checkbox','radio'].includes(c.type)||c.checked)).map(c=>[c.name,c.value || (c.type==='checkbox'?'on':'')]);}has(key){return this.data.some(([name])=>name===key);}get(key){return this.data.find(([name])=>name===key)?.[1]??null;}getAll(key){return this.data.filter(([name])=>name===key).map(([,v])=>v);}entries(){return this.data.values();}};
 const context={workUI,crypto:cryptoProvider,AbortController,FormData,document:{activeElement:null},console,proposalChangesObserver};vm.createContext(context);const observedSource=proposalChangesObserver?source.replace('function proposalChanges(before,after) {','function proposalChanges(before,after) { proposalChangesObserver();'):source;vm.runInContext(observedSource,context);context.callbacks=callbacks;h.designer=vm.runInContext('createWorkDesigner({callbacks})',context);h.helpers=vm.runInContext('workAuthoring',context);h.host=host;h.callbacks=callbacks;h.document=context.document;
 h.render=()=>h.designer.render({state:h.state,selection:h.selection,host});h.render();
 h.click=(action,data={})=>{const button=h.buttons.find(node=>node.dataset.authorAction===action&&Object.entries(data).every(([key,value])=>node.dataset[key]===value));button?.focus();const control={dataset:{authorAction:action,...data}};h.designer.handleEvent({type:'click',target:button || {closest:selector=>selector==='#ees-work-designer'?host:selector==='[data-author-action]'?control:null}});};
 // The outer work host captures overlay clicks before workUI.dialog settles its promise.
 h.clickDialogCancel=()=>{assert.ok(dialog,'a confirmation overlay is open');const target={tagName:'BUTTON',id:'ees-work-dialog-cancel',closest:selector=>{const selectors=selector.split(',').map(value=>value.trim());return selectors.includes('[data-dialog-cancel]')?target:selectors.includes('#ees-work-dialog')?dialog:null;}};h.document.activeElement=target;return h.designer.handleEvent({type:'click',target,preventDefault:noop,stopPropagation:noop});};
 h.field=(name,value,event='input')=>{const field=h.fields.find(f=>(f.name===name || f.id===name)&&(f.type!=='radio'||f.value===value));assert.ok(field,'field '+name);if(field.type==='checkbox')field.checked=value;else if(field.type==='radio'){for(const item of h.fields.filter(f=>f.name===name))item.checked=item===field;}else field.value=value;field.focus();h.designer.handleEvent({type:event,target:field});};
 h.pick=async(id)=>{h.click('tool_create');await flush();h.click('tool_pick',{id});await flush();};h.example=async(id)=>{h.click('tool_create');await flush();h.click('tool_example',{id});await flush();};h.chooseTemplate=async value=>{const field=h.fields.find(field=>field.name==='procedure_template'&&field.value===value);assert.ok(field,'procedure radio '+value);for(const item of h.fields.filter(item=>item.name==='procedure_template'))item.checked=item===field;h.designer.handleEvent({type:'change',target:{...field,closest:()=>host}});await flush();};h.node=async(id='j')=>{h.click('node',{id});await flush();};h.open=async id=>{await callbacks.openWorkflow(id);};h.draft=()=>copy(h.designer.readDraft());h.proposal=(definitionValue,extra={})=>h.designer.acceptProposal({workflow_id:h.selection.workflow_id,base_revision:h.draft().revision,context_id:'native-context',definition:copy(definitionValue),...extra},{chatId:h.selection.chat_id});h.inline=async(name)=>{h.field('name',name);h.click('inline_apply');await flush();};h.escape=selector=>h.designer.handleEvent({type:'keydown',key:'Escape',target:{closest:query=>query==='#ees-work-designer'?host:query===selector?h.host.querySelector(selector):null}});return h;
}

async function beginCreation(h,name='',description=''){h.click('create');await flush();assert.ok(h.forms['ew-procedure-create']);h.field('ew-procedure-name',name);h.field('ew-procedure-description',description);}
async function submitCreation(h){h.click('procedure_create');await flush();}

test('new Figma authoring keeps Native conversation untouched and has exact right-panel structure',async()=>{const h=harness();await flush();assert.match(h.markup,/class="ew-author(?:\s[^"]*)?"/);assert.match(h.markup,/업무 내용/);assert.doesNotMatch(h.markup,/data-tab="(?:summary|structure)"/);assert.doesNotMatch(source,/hideWorkspaceContent|chat\.hidden|ees-work-native-hidden/);});
test('C66 content removes the needed-summary surface while preserving stored review decisions',async()=>{
 const h=harness(),value=definition();value.authoring_review={inputs:true,rules:false,custom:{keep:'opaque'}};installDefinition(h,value);
 assert.doesNotMatch(h.markup,/정해야 할 것|data-author-action="summary_open"|ew-content-needs/);
 await h.node();h.field('job_guidance','검토 기록을 보존할 안내');h.click('save');await flush();
 assert.deepEqual(h.writes.at(-1).definition.authoring_review,value.authoring_review);assert.equal(h.writes.at(-1).definition.nodes.j.instructions,'검토 기록을 보존할 안내');
});
test('C66 expanded stages keep edit visible and disclose move and delete only through their menu',async()=>{
 const h=harness();installDefinition(h,stagedDefinition(3));
 assert.equal(h.buttons.some(button=>button.dataset.authorAction==='stage_menu'),false);
 h.click('stage_toggle',{id:'t1'});await flush();assert.ok(actionButton(h,'stage_edit','t1'));assert.ok(actionButton(h,'stage_menu','t1'));
 for(const action of ['move_up','move_down','delete_node'])assert.equal(Boolean(actionButton(h,action,'t1')),false,action+' is not an always-visible stage action');
 h.click('stage_menu',{id:'t1'});await flush();assert.equal(actionButton(h,'stage_menu','t1').getAttribute('aria-expanded'),'true');
 for(const action of ['move_up','move_down','delete_node'])assert.ok(actionButton(h,action,'t1'),action+' is available in the open menu');
 assert.equal(h.writes.length,0);assert.equal(h.draft().dirty,false);
});
test('C66 stage menu Escape closes only an open menu and restores its trigger',async()=>{
 const h=harness();installDefinition(h,stagedDefinition(2));h.click('stage_toggle',{id:'t0'});await flush();
 const escape=()=>h.designer.handleEvent({type:'keydown',key:'Escape',target:actionButton(h,'stage_menu','t0')});
 assert.ok(actionButton(h,'stage_menu','t0'));actionButton(h,'stage_menu','t0').focus();assert.deepEqual(copy(escape()),{handled:false,preventDefault:false});
 h.click('stage_menu',{id:'t0'});await flush();assert.deepEqual(copy(escape()),{handled:true,preventDefault:true});
 assert.equal(actionButton(h,'stage_menu','t0').getAttribute('aria-expanded'),'false');assert.equal(h.document.activeElement,actionButton(h,'stage_menu','t0'));
 assert.equal(stageButton(h,'t0').getAttribute('aria-expanded'),'true');assert.equal(h.draft().dirty,false);assert.equal(h.writes.length,0);
});
test('C66 outside clicks close stage and job menus while preserving the clicked focus and draft',async()=>{
 for(const [action,id] of [['stage_menu','t0'],['job_menu','j0-0']]){
  const h=harness();installDefinition(h,stagedDefinition(2));h.click('stage_toggle',{id:'t0'});h.click(action,{id});await flush();assert.equal(actionButton(h,action,id).getAttribute('aria-expanded'),'true');const before=h.draft();
  const outside={id:'conversation-editor',closest:()=>null};h.document.activeElement=outside;h.designer.handleEvent({type:'click',target:outside});await flush();
  assert.equal(actionButton(h,action,id).getAttribute('aria-expanded'),'false');assert.equal(h.document.activeElement,outside);assert.deepEqual(h.draft(),before);assert.equal(h.writes.length,0);
 }
});
for(const view of ['stage','job detail'])test('C66 cancelling deletion closes the '+view+' menu and returns focus without changing the draft',async()=>{
 const h=harness();installDefinition(h,stagedDefinition(2));h.click('stage_toggle',{id:'t0'});await flush();
 const id=view==='stage'?'t0':'j0-0',action=view==='stage'?'stage_menu':'job_menu';if(view==='job detail')await h.node(id);
 h.click(action,{id});await flush();assert.equal(actionButton(h,action,id).getAttribute('aria-expanded'),'true');const before=h.draft();
 h.dialogs.push(null);h.click('delete_node',{id});await flush();assert.equal(h.dialogHistory.length,1);assert.equal(h.dialogHistory[0].confirmLabel,'초안에서 삭제');
 assert.deepEqual(h.draft(),before);assert.equal(h.writes.length,0);assert.equal(h.operations.length,0);
 assert.equal(actionButton(h,action,id).getAttribute('aria-expanded'),'false');assert.equal(h.document.activeElement,actionButton(h,action,id));
 if(view==='stage')assert.equal(stageButton(h,id).getAttribute('aria-expanded'),'true');else assert.ok(h.forms['ew-author-node']);
});
for(const view of ['stage','job detail'])test('C66 clicking dialog Cancel restores the '+view+' menu trigger after the host capture event',async()=>{
 const h=harness();installDefinition(h,stagedDefinition(2));h.click('stage_toggle',{id:'t0'});await flush();
 const id=view==='stage'?'t0':'j0-0',action=view==='stage'?'stage_menu':'job_menu';if(view==='job detail')await h.node(id);
 h.click(action,{id});await flush();const before=h.draft();assert.equal(actionButton(h,action,id).getAttribute('aria-expanded'),'true');
 let captured=false;h.dialogs.push(null);h.dialogHook=()=>{captured=true;assert.deepEqual(copy(h.clickDialogCancel()),{handled:false,preventDefault:false});};
 h.click('delete_node',{id});await flush();assert.equal(captured,true);assert.equal(h.dialogHistory.length,1);
 assert.deepEqual(h.draft(),before);assert.equal(h.writes.length,0);assert.equal(h.operations.length,0);
 assert.equal(actionButton(h,action,id).getAttribute('aria-expanded'),'false');assert.equal(h.document.activeElement,actionButton(h,action,id));
 if(view==='stage')assert.equal(stageButton(h,id).getAttribute('aria-expanded'),'true');else assert.ok(h.forms['ew-author-node']);
});
test('C66 a stale deletion cancellation cannot close another workflow menu with the same stage ID',async()=>{
 const h=harness(),other=stagedDefinition(1);other.id='q';other.name='다른 절차';h.workflows.get('q').draft=copy(other);installDefinition(h,stagedDefinition(2));h.click('stage_toggle',{id:'t0'});h.click('stage_menu',{id:'t0'});await flush();
 h.dialogs.push(null);h.dialogHook=async()=>{await h.open('q');h.click('stage_toggle',{id:'t0'});h.click('stage_menu',{id:'t0'});await flush();};h.click('delete_node',{id:'t0'});await flush();
 assert.equal(h.draft().definition.id,'q');assert.deepEqual(h.draft().definition,other);assert.equal(actionButton(h,'stage_menu','t0').getAttribute('aria-expanded'),'true');assert.equal(h.document.activeElement,actionButton(h,'stage_menu','t0'));assert.equal(h.writes.length,0);
});
for(const scope of [undefined,'system','factory'])for(const count of [0,1])for(const saved of [false,true])test(`A12 sidebar owns factory scope while content inspection preserves overrides: ${scope || 'undecided'} / ${count} / ${saved}`,async()=>{
 const h=harness(),value=definition();if(scope)value.execution_scope=scope;h.state.factories=count?[{id:'f',name:'공장'}]:[];
 h.workflows.get('w').settings=saved?[{factory_id:'f',revision:2,values:{target:'보존할 공장 값'}}]:[{factory_id:'',revision:1,values:{target:'기본값'}}];installDefinition(h,value);
 const settings=copy(h.workflows.get('w').settings);assert.doesNotMatch(h.markup,/class="ew-author-factories"/);h.selection.factory_id=count?'f':'';h.render();assert.deepEqual(h.workflows.get('w').settings,settings);
 assert.deepEqual(h.draft().definition,value);assert.equal(h.draft().dirty,false);assert.equal(h.writes.length,0);
});
test('A12 sidebar scope and tab visits preserve existing factory conditions and saved overrides',async()=>{
 const h=harness(),value=definition();value.execution_scope='factory';value.nodes.j.condition={field:'factory_id',op:'eq',value:'f'};h.workflows.get('w').settings=[{factory_id:'f',revision:2,values:{target:'공장별 원래값'}},{factory_id:'',revision:1,values:{target:'기본값'}}];const settings=copy(h.workflows.get('w').settings);installDefinition(h,value);
 h.selection.factory_id='f';h.render();assert.doesNotMatch(h.markup,/class="ew-author-factories"/);await h.node();h.click('node',{id:''});await flush();h.click('tab',{tab:'schedule'});await flush();h.click('tab',{tab:'content'});await flush();
 assert.deepEqual(h.draft().definition,value);assert.deepEqual(h.workflows.get('w').settings,settings);assert.equal(h.writes.length,0);assert.equal(h.operations.length,0);assert.equal(h.draft().dirty,false);
});
test('A12 explicit settings editing uses the sidebar factory while browsing and cancellation never write overrides',async()=>{
 const h=harness(),value=definition();value.execution_scope='factory';value.nodes.j.inputs=[{id:'target',name:'대상',type:'text',scope:'workflow'}];h.workflows.get('w').settings=[{factory_id:'f',revision:2,values:{target:'공장별 원래값'}},{factory_id:'',revision:1,values:{target:'기본값'}}];const settings=copy(h.workflows.get('w').settings);installDefinition(h,value);h.selection.factory_id='f';h.render();assert.equal(h.writes.length,0);
 h.dialogs.push(null);h.click('factory_settings');await flush();assert.equal(h.dialogHistory.at(-1).title,'공장별 업무 설정');assert.match(h.dialogHistory.at(-1).html,/공장별 원래값/);assert.equal(h.writes.length,0);assert.deepEqual(h.workflows.get('w').settings,settings);
 h.dialogs.push({'override:target':true,'value:target':'명시적으로 고친 공장 값'});h.click('factory_settings');await flush();assert.equal(h.writes.length,1);assert.equal(h.writes[0].factory_id,'f');assert.equal(h.writes[0].expected_revision,2);assert.deepEqual(h.writes[0].values,{target:'명시적으로 고친 공장 값'});
 h.selection.factory_id='';h.render();h.dialogs.push(null);h.click('factory_settings');await flush();assert.equal(h.dialogHistory.at(-1).title,'기본 업무 설정');assert.match(h.dialogHistory.at(-1).html,/기본값/);assert.equal(h.writes.length,1);assert.deepEqual(h.draft().definition,value);assert.equal(h.draft().dirty,false);assert.equal(h.operations.length,0);
});
test('C66 losing factory visibility removes hidden selection without changing saved factory values',async()=>{
 const h=harness(),value=definition();value.execution_scope='factory';value.nodes.j.inputs=[{id:'target',name:'대상',type:'text',scope:'workflow'}];installDefinition(h,value);h.click('factory',{id:'f'});await flush();
 h.click('summary_edit',{id:'business'});await flush();h.field('execution_scope','system','change');h.click('summary_apply');await flush();assert.doesNotMatch(h.markup,/class="ew-author-factories"/);
 h.dialogs.push({'override:target':true,'value:target':'기본에만 저장'});h.click('factory_settings');await flush();assert.equal(h.writes.at(-1).factory_id,'');
 assert.deepEqual(h.writes.at(-1).values,{target:'기본에만 저장'});assert.equal(h.draft().definition.execution_scope,'system');
});
test('name-only creation does not publish the retired example-helper screen',async()=>{const h=harness();await h.open('');h.click('create');await flush();assert.ok(h.forms['ew-procedure-create']);assert.doesNotMatch(h.markup,/procedure_template|예시에서 시작|직접 만들기/);h.click('procedure_cancel');await flush();assert.equal(h.writes.length,0);});
test('empty workspace listing does not create drafts or runs',async()=>{const h=harness();h.state.workflows=[];await h.open('');assert.match(h.markup,/아직 워크플로우가 없습니다/);assert.equal(h.writes.length,0);assert.equal(h.operations.length,0);});
test('direct editing saves only the chosen definition with current revision and request ID',async()=>{const h=harness();await h.node();h.field('job_guidance','직접 수정');h.click('save');await flush();assert.equal(h.writes[0].action,'save_draft');assert.equal(h.writes[0].workflow_id,'w');assert.equal(h.writes[0].expected_revision,1);assert.ok(h.writes[0].request_id);assert.equal(h.writes[0].definition.nodes.j.instructions,'직접 수정');assert.equal(h.workflows.get('q').draft.nodes.j.instructions,'원래 안내');assert.equal(h.draft().revision,2);assert.equal(h.draft().dirty,false);});
test('dirty drafts and per-workflow node selection survive navigation',async()=>{const h=harness();await h.node();h.field('job_guidance','W 비공개 초안');await h.open('q');await h.node();h.field('job_guidance','Q 초안');await h.open('w');assert.equal(h.draft().definition.nodes.j.instructions,'W 비공개 초안');assert.match(h.markup,/W 비공개 초안/);assert.equal(h.writes.length,0);});
test('typing during save preserves later edits and acknowledges only own base revision',async()=>{const h=harness(),pending=deferred();await h.node();h.field('job_guidance','저장 요청');h.writeOverride=()=>pending.promise;h.click('save');await flush();h.field('job_guidance','요청 뒤 새 글');pending.resolve({ok:true,revision:2});await flush();assert.equal(h.draft().definition.nodes.j.instructions,'요청 뒤 새 글');assert.equal(h.draft().revision,2);assert.equal(h.draft().dirty,true);});
test('same failed payload reuses request identity; different payload receives new identity',async()=>{const h=harness();await h.node();h.writeOverride=async()=>{throw new Error('response lost');};h.field('job_guidance','첫 글');h.click('save');await flush();h.click('save');await flush();assert.equal(h.writes[0].request_id,h.writes[1].request_id);h.field('job_guidance','다른 글');h.click('save');await flush();assert.notEqual(h.writes[1].request_id,h.writes[2].request_id);});
test('revision conflict preserves unsaved text and never silently rebases',async()=>{const h=harness();await h.node();h.field('job_guidance','충돌 전 글');h.writeOverride=async()=>({ok:false,error:{code:'revision_conflict',message:'다른 담당자가 저장했습니다.'}});h.click('save');await flush();assert.equal(h.draft().revision,1);assert.equal(h.draft().dirty,true);assert.equal(h.draft().definition.nodes.j.instructions,'충돌 전 글');assert.match(h.markup,/최신 저장본과 비교/);});
test('authorization denial preserves private draft and blocks subsequent mutation',async()=>{const h=harness();await h.node();h.field('job_guidance','권한 회수 전 글');h.writeOverride=async()=>{throw Object.assign(new Error('권한 회수'),{status:403});};h.click('save');await flush();h.click('save');await flush();assert.equal(h.writes.length,1);assert.equal(h.designer.canAuthor(),false);assert.equal(h.draft().definition.nodes.j.instructions,'권한 회수 전 글');});
test('account reset rejects late save and clears draft cache',async()=>{const h=harness(),pending=deferred();await h.node();h.field('job_guidance','A 비공개');h.writeOverride=()=>pending.promise;h.click('save');await flush();h.state.capabilities.actor_id='b';h.render();pending.resolve({ok:true,revision:99});await flush();assert.doesNotMatch(h.markup,/A 비공개/);assert.notEqual(h.draft().revision,99);});
test('late workflow reads cannot overwrite newer selection',async()=>{const h=harness(),pending=deferred();h.state.workflow=null;h.state.workflows=h.state.workflows.map(({draft,...rest})=>rest);h.readOverride=q=>q.workflow_id==='q'?pending.promise:Promise.resolve({workflow:copy(h.workflows.get('w'))});await h.open('q');await h.open('w');pending.resolve({workflow:copy(h.workflows.get('q'))});await flush();assert.equal(h.draft().definition.id,'w');});
test('publish requires exact saved validated revision and explicit confirmation',async()=>{const h=harness();await h.node();h.field('job_guidance','저장 전 변경');h.click('publish');await flush();assert.equal(h.writes.length,0);h.click('save');await flush();h.click('validate');await flush();h.dialogs.push(null);h.click('publish');await flush();assert.equal(h.writes.filter(w=>w.action==='publish_workflow').length,0);h.dialogs.push({});h.click('publish');await flush();const body=h.writes.at(-1);assert.equal(body.action,'publish_workflow');assert.equal(body.expected_revision,2);assert.match(h.dialogHistory.at(-1).html,/기존 진행 건은 바뀌지 않습니다/);});
test('all eight input types and result blocks are represented without workflow-specific HTML',()=>{const h=harness();assert.equal(Object.keys(h.helpers.inputTypes).length,8);assert.equal(Object.keys(h.helpers.blocks).length,8);assert.deepEqual(Object.keys(h.helpers.inputTypes),['text','number','datetime','single','multi','list','person','boolean']);assert.ok(h.helpers.blocks.change_request);});
test('declared input and tool argument binding are saved together',async()=>{const h=harness();await h.node();h.dialogs.push({id:'project',name:'Jira 프로젝트',type:'single',scope:'workflow',required:true,unit:'',options_source:'manual',options:'PROJA\nPROJB',depends_on:'',tool_argument:'project_key'});h.click('input_add');await flush();const node=h.draft().definition.nodes.j;assert.equal(node.inputs[0].id,'project');assert.equal(node.inputs[0].required,true);assert.deepEqual(node.inputs[0].options,['PROJA','PROJB']);assert.deepEqual(node.argument_bindings.project_key,{input:'project'});assert.equal(node.inputs[0].scope,'workflow');});
test('stage/job insertion and removal keep referential defects visible for publish validation',async()=>{const h=harness();h.click('add_stage');await flush();await h.inline('추가 단계');const stage=Object.values(h.draft().definition.nodes).find(n=>n.id.startsWith('stage-'));assert.equal(stage.parent,'p');h.click('add_job',{parent:stage.id});await flush();await h.inline('추가 작업');const job=Object.values(h.draft().definition.nodes).find(n=>n.id.startsWith('job-'));assert.equal(job.parent,stage.id);const d=h.draft().definition;d.nodes.j.deps=[job.id];const removed=h.helpers.removeNode(d,stage.id);assert.ok(removed.includes(job.id));assert.deepEqual(d.nodes.j.deps,[job.id]);assert.ok(d.nodes.j);});
test('factory overrides distinguish an explicit empty value, zero, and absent value',async()=>{const h=harness();h.workflows.get('w').draft.execution_scope='factory';h.workflows.get('w').draft.nodes.j.inputs=[{id:'target',name:'대상',type:'text',scope:'workflow'},{id:'limit',name:'한도',type:'number',scope:'workflow'},{id:'unused',name:'기본 사용',type:'text',scope:'workflow'}];h.selection.factory_id='f';h.render();h.dialogs.push({'override:target':true,'value:target':'','override:limit':true,'value:limit':'0','override:unused':false,'value:unused':'무시'});h.click('factory_settings');await flush();const body=h.writes.at(-1);assert.equal(body.action,'save_settings');assert.equal(body.factory_id,'f');assert.deepEqual(body.values,{target:'',limit:0});});
test('authoring panel never requests model metadata or offers an AI request form',async()=>{const h=harness();await flush();assert.equal(h.modelReads || 0,0);assert.equal(h.proposals.length,0);assert.doesNotMatch(h.markup,/name="(?:model_id|ai_prompt)"|data-author-action="ai_(?:propose|cancel)"|초안 제안 요청|대화로 절차 초안 만들기/);assert.doesNotMatch(source,/callbacks\.propose|async function propose\(|aiController/);});

test('0 models and model listing failure preserve direct authoring and save',async()=>{for(const fails of [false,true]){const h=harness();h.designer.reset();h.modelsOverride=async()=>{if(fails)throw new Error('no model listing');return {models:[]};};h.render();await flush();await h.node();h.field('job_guidance','모델 없이 작성');h.click('save');await flush();assert.equal(h.writes[0].definition.nodes.j.instructions,'모델 없이 작성');assert.equal(h.proposals.length,0);assert.equal(h.modelReads || 0,0);}});

test('Native model choices never introduce panel request controls',async()=>{for(const models of [[{id:'m'}],[{id:'a'},{id:'b'}]]){const h=harness();h.modelsOverride=async()=>({models});h.render();await flush();assert.doesNotMatch(h.markup,/name="model_id"/);assert.equal(h.buttons.some(b=>['ai_propose','ai_cancel'].includes(b.dataset.authorAction)),false);assert.equal(h.modelReads || 0,0);}});

test('AI proposal is a preview and explicit local application never saves or publishes',async()=>{const h=harness();await flush();h.proposal({...definition(),name:'AI 제안'});assert.equal(h.draft().definition.name,'절차 w');assert.match(h.markup,/업무 도우미 제안 · 반영 전/);assert.equal(h.writes.length,0);h.click('ai_apply');await flush();assert.equal(h.draft().definition.name,'AI 제안');assert.equal(h.draft().dirty,true);assert.equal(h.writes.length,0);});

test('late AI proposal after workflow navigation or manual edits is never applied',async()=>{for(const navigate of [false,true]){const h=harness();await flush();const proposal={workflow_id:'w',base_revision:1,context_id:'native-context',definition:{...definition(),name:'적용 금지'}};if(navigate){await h.open('q');assert.throws(()=>h.designer.acceptProposal(proposal,{chatId:'private-chat'}));}else{h.designer.acceptProposal(proposal,{chatId:'private-chat'});await h.node();h.field('job_guidance','새로 직접 작성');h.click('ai_apply');await flush();assert.match(h.markup,/초안이 바뀌어|지난 제안/);assert.equal(h.draft().definition.nodes.j.instructions,'새로 직접 작성');}assert.notEqual(h.draft().definition.name,'적용 금지');assert.equal(h.writes.length,0);}});

test('malformed and cross-context AI output cannot create arbitrary editor state',()=>{const h=harness();const context={workflowId:'w',revision:1,contextId:'c'},good={workflow_id:'w',base_revision:1,context_id:'c',definition:definition()};for(const bad of ['not json',{...good,workflow_id:'q'},{...good,base_revision:2},{...good,context_id:'d'},{...good,definition:{nodes:[{id:'x',type:'script'}]}}])assert.throws(()=>h.helpers.proposal(bad,context));assert.equal(h.helpers.proposal(good,context).definition.id,'w');});
test('Native chat proposals require exact personal conversation and target revision',()=>{const h=harness(),proposal={workflow_id:'w',base_revision:1,context_id:'c',definition:definition()};assert.throws(()=>h.designer.acceptProposal(proposal,{chatId:'someone-else'}));assert.throws(()=>h.designer.acceptProposal({...proposal,base_revision:2},{chatId:'private-chat'}));assert.equal(h.designer.acceptProposal(proposal,{chatId:'private-chat'}).saved,false);assert.equal(h.writes.length,0);});
test('B5 stores inspected Native function reference and immutable input schema',async()=>{const h=harness();h.selection.tab='tools';h.state.native_functions=[{name:'Jira',kind:'read',reference:{tool_id:'jira',function:'search_issues',code_hash:'sha'},schema:{type:'object',properties:{project:{type:'string'}}}}];h.render();await h.pick('jira:search_issues');h.field('name','CR 조회');h.click('tool_save');await flush();assert.equal(h.operations[0].action,'tool_save');assert.deepEqual(h.operations[0].tool.reference,{tool_id:'jira',function:'search_issues',code_hash:'sha'});assert.deepEqual(h.operations[0].tool.input_schema,{type:'object',properties:{project:{type:'string'}}});assert.equal(h.writes.length,0);});
test('tool review is an explicit operation with designated contract revision',async()=>{const h=harness();h.selection.tab='tools';h.state.tools=[{id:'tool',name:'조회',kind:'read',system_id:'EMS',revision:3,state:'review_requested'}];h.render();h.click('tool_open',{id:'tool'});h.dialogs.push({review_note:'기능과 가이드 확인',review_evidence:'repo/commit · contract test · local synthetic environment'});h.click('tool_approve');await flush();assert.equal(h.operations[0].action,'tool_review');assert.equal(h.operations[0].decision,'approve');assert.equal(h.operations[0].tool_contract_id,'tool');assert.equal(h.operations[0].expected_revision,3);assert.match(h.operations[0].evidence,/contract test/);});
test('unavailable EES definitions are explicit and never turn into fake request success',async()=>{const h=harness();h.selection.tab='tools';h.render();await h.example('restart-service');assert.match(h.markup,/필요한 기능이 아직 연결되지 않았습니다/);assert.equal(h.buttons.find(button=>button.dataset.authorAction==='tool_review').disabled,true);assert.equal(h.operations.length,0);assert.doesNotMatch(h.markup,/실행 성공/);});
test('unsafe labels and instructions are escaped in the editor',async()=>{const h=harness();h.workflows.get('w').draft.nodes.j.name='<img onerror="attack">';h.workflows.get('w').draft.nodes.j.instructions='<script>attack()</script>';h.render();await h.node();assert.doesNotMatch(h.markup,/<script>/);assert.match(h.markup,/&lt;script&gt;/);assert.match(h.markup,/&lt;img/);});

test('opening a form and reading a draft never marks unchanged definitions dirty',async()=>{const h=harness(),original=copy(h.workflows.get('w').draft);await h.node();assert.deepEqual(h.draft().definition,original);assert.equal(h.draft().dirty,false);h.click('tab',{tab:'schedule'});await flush();assert.deepEqual(h.draft().definition,original);assert.equal(h.draft().dirty,false);});
test('opaque Native references, dangling dependencies and compound conditions survive unrelated edits',async()=>{const h=harness(),node=h.workflows.get('w').draft.nodes.j;node.tool_reference={tool_id:'private',function:'read',code_hash:'old'};node.deps=['removed'];node.argument_bindings={target:{input:'hidden-input'}};node.condition={all:[{field:'country',op:'eq',value:'KR'},{field:'interface',op:'eq',value:false}]};h.render();await h.node();h.field('job_guidance','안내만 수정');const result=h.draft().definition.nodes.j;assert.deepEqual(result.tool_reference,node.tool_reference);assert.deepEqual(result.deps,['removed']);assert.deepEqual(result.condition,node.condition);assert.deepEqual(result.argument_bindings,node.argument_bindings);});
test('factory settings preserve all eight input value types without coercing omitted fields',async()=>{const h=harness();const inputs=Object.keys(h.helpers.inputTypes).map((type,i)=>({id:'f'+i,name:type,type,scope:'workflow',options:['a','b']}));h.workflows.get('w').draft.nodes.j.inputs=inputs;h.render();const raw=['text','0','2026-10-03T10:30','a',['a','b'],'first\nsecond','group:operators','false'];const answer={};for(let i=0;i<inputs.length;i++){answer['override:f'+i]=true;answer['value:f'+i]=raw[i];}h.dialogs.push(answer);h.click('factory_settings');await flush();assert.deepEqual(h.writes.at(-1).values,{f0:'text',f1:0,f2:'2026-10-03T10:30',f3:'a',f4:['a','b'],f5:['first','second'],f6:{kind:'group',id:'operators'},f7:false});});
test('late Native proposal after reset cannot expose the previous account preview',async()=>{const h=harness(),late={workflow_id:'w',base_revision:1,context_id:'a-context',definition:{...definition(),name:'A 비공개 제안'}};h.proposal(late.definition);h.designer.reset();h.state.capabilities.actor_id='b';h.selection.chat_id='b-chat';h.render();assert.throws(()=>h.designer.acceptProposal(late,{chatId:'private-chat'}));assert.doesNotMatch(h.markup,/A 비공개 제안/);assert.equal(h.buttons.some(button=>button.dataset.authorAction==='ai_apply'),false);assert.equal(h.writes.length,0);});

test('a confirmation opened for one workflow cannot publish after context changes',async()=>{const h=harness();h.dialogs.push({});h.dialogHook=()=>h.open('q');h.click('publish');await flush();assert.equal(h.writes.length,0);assert.equal(h.draft().definition.id,'q');});
test('conflict comparison can discard only by explicit choice and load exact new revision',async()=>{const h=harness();await h.node();h.field('job_guidance','내 변경');h.workflows.get('w').revision=3;h.workflows.get('w').draft.nodes.j.instructions='서버 변경';h.dialogs.push({choice:'keep'});h.click('compare');await flush();assert.equal(h.draft().definition.nodes.j.instructions,'내 변경');assert.equal(h.draft().revision,1);h.dialogs.push({choice:'discard'});h.click('compare');await flush();assert.equal(h.draft().definition.nodes.j.instructions,'서버 변경');assert.equal(h.draft().revision,3);assert.equal(h.draft().dirty,false);});
test('tool navigation returns to workflow editor without retaining tool-only surface',async()=>{const h=harness();h.selection.tab='tools';h.render();assert.match(h.markup,/>도구 · 공용</);h.selection.tab='overview';h.render();assert.match(h.markup,/워크스페이스 · 워크플로우/);assert.match(h.markup,/워크플로우 정보·분류 수정/);});
test('hidden job trigger remains a stored offset after direct guidance editing',async()=>{const h=harness();h.workflows.get('w').draft.nodes.j.trigger={offset_seconds:3600};h.render();await h.node();assert.equal(h.fields.some(f=>f.name==='trigger_kind'),false);h.field('job_guidance','안내만 수정');h.click('save');await flush();assert.deepEqual(h.writes[0].definition.nodes.j.trigger,{offset_seconds:3600});assert.doesNotMatch(source,/setInterval|setTimeout/);});

test('published periodic schedule explicitly pins user, version, jobs, timezone and delegation',async()=>{const h=harness(),record=h.workflows.get('w');record.published_version=2;record.draft.mode='periodic';record.draft.schedule={timezone:'Asia/Seoul',anchor:'2026-10-05T09:00',frequency:'weekly',interval:1};record.draft.nodes.j.mode='tool';record.published=copy(record.draft);h.render();h.click('schedule_tools');h.dialogs.push({timezone:'Asia/Seoul',anchor:'2026-10-05T09:00',frequency:'weekly',interval:'1',grace_seconds:'300',delegated:true,'job:j':true});h.click('schedule_create');await flush();assert.equal(h.operations[0].action,'schedule_save');assert.equal(h.operations[0].expected_revision,0);assert.equal(h.operations[0].schedule.identity_user_id,'a');assert.equal(h.operations[0].schedule.version,2);assert.equal(h.operations[0].schedule.delegated,true);assert.deepEqual(h.operations[0].schedule.job_ids,['j']);assert.equal(h.operations[0].schedule.catch_up,'miss');assert.equal(h.writes.length,0);});

test('hidden Native skills retain their saved IDs and do not acquire newly available skills',async()=>{const h=harness();h.workflows.get('w').draft.nodes.j.skills=['saved-skill'];h.callbacks.resources=async()=>({available:true,skills:[{id:'native-skill',name:'사용자 지침',revision:4}]});h.render();await flush();await h.node();assert.equal(h.fields.some(f=>f.name==='skills'),false);h.field('job_guidance','안내 변경');h.click('save');await flush();assert.deepEqual(h.writes[0].definition.nodes.j.skills,['saved-skill']);assert.equal(JSON.stringify(h.writes[0]).includes('skill body'),false);});

test('unavailable Native skills preserve opaque references and do not block direct human work',async()=>{const h=harness();h.workflows.get('w').draft.nodes.j.skills=['opaque-skill'];h.callbacks.resources=async()=>({available:false,skills:[]});h.render();await flush();await h.node();h.field('job_guidance','직접 작성 가능');h.click('save');await flush();assert.deepEqual(h.writes[0].definition.nodes.j.skills,['opaque-skill']);assert.equal(h.writes[0].definition.nodes.j.mode,'human');assert.equal(h.fields.some(f=>f.name==='skills'),false);});
test('a late skill-list response cannot expose the previous account metadata',async()=>{const h=harness(),pending=deferred();h.callbacks.resources=()=>pending.promise;h.render();await flush();h.designer.reset();h.state.capabilities.actor_id='b';h.callbacks.resources=async()=>({available:true,skills:[]});h.render();await flush();pending.resolve({available:true,skills:[{id:'a-private',name:'A 비공개 지침'}]});await flush();await h.node();assert.doesNotMatch(h.markup,/A 비공개 지침/);});

test('dynamic Jira options pin discovered Native reference and declared project dependency without static examples',async()=>{const h=harness(),reference={tool_id:'jira-native',function:'jira_project_metadata',revision:7,content_hash:'current'};h.state.native_functions=[{kind:'read',name:'Jira metadata',reference}];await h.node();h.dialogs.push({id:'cr_status',name:'CR 상태',type:'multi',scope:'run',required:true,options_source:'tool',source_reference:'jira-native:jira_project_metadata',source_list:'statuses',depends_on:'project',options:'must disappear',tool_argument:'status_ids'});h.click('input_add');await flush();const field=h.draft().definition.nodes.j.inputs[0];assert.deepEqual(field.depends_on,['project']);assert.deepEqual(field.options,[]);assert.deepEqual(field.options_query,{reference,argument_bindings:{project_key:{input:'project'}},result_path:['statuses'],value_field:'id',label_field:'name'});assert.equal(field.source_reference,undefined);});
test('dynamic options cannot invent an unconfigured Native reference or fall back to static entries',async()=>{const h=harness();await h.node();h.dialogs.push({id:'project',name:'프로젝트',type:'single',scope:'run',options_source:'tool',source_reference:'not-permitted',source_list:'projects',options:'EMS'});h.click('input_add');await flush();assert.deepEqual(h.draft().definition.nodes.j.inputs,[]);assert.match(h.markup,/현재 계정으로 확인한 선택지 조회 기능/);});
test('common options use current authorized entities and preserve an opaque tool source on description edit',async()=>{const h=harness(),query={reference:{tool_id:'private',function:'custom'},argument_bindings:{x:{constant:'fixed'}},result_path:['permitted'],value_field:'key',label_field:'title'};h.workflows.get('w').draft.nodes.j.inputs=[{id:'opaque',name:'기존',type:'single',scope:'run',options_source:'tool',options_query:query,depends_on:[]}];h.render();await h.node();h.dialogs.push({id:'opaque',name:'설명만 변경',type:'single',scope:'run',options_source:'tool',source_reference:'private:custom'});h.click('input_edit',{id:'opaque'});await flush();assert.deepEqual(h.draft().definition.nodes.j.inputs[0].options_query,query);h.dialogs.push({id:'group',name:'그룹',type:'single',scope:'run',options_source:'common',source_common:'groups',options:'fake'});h.click('input_add');await flush();assert.deepEqual(h.draft().definition.nodes.j.inputs[1].options_query,{kind:'groups'});assert.deepEqual(h.draft().definition.nodes.j.inputs[1].options,[]);});
test('tool selection pins contract revision and unrelated edits cannot silently upgrade an old published reference',async()=>{const h=harness(),reference={tool_id:'native',function:'read',content_hash:'v2'};h.state.tools=[{id:'approved-tool',name:'승인된 읽기',state:'approved',revision:2,reference,input_schema:{properties:{}}}];await h.node();await a12Connect(h,'approved-tool',{shared:false});assert.equal(h.draft().definition.nodes.j.tool_contract_revision,2);h.state.tools[0].revision=3;h.state.tools[0].reference={...reference,content_hash:'v3'};h.field('job_guidance','안내만 수정');const node=h.draft().definition.nodes.j;assert.equal(node.tool_contract_revision,2);assert.equal(node.tool_reference.content_hash,'v2');});

test('existing AI item sources and EES effect criteria survive visible guidance edits',async()=>{const h=harness(),value=definition();Object.assign(value.nodes.j,{mode:'ai',result_block:'change_request',result_source_job_id:'cr-list',effect_criterion:{job_id:'verify',description:'승인된 상태 조회에서 효과를 확인'}});installDefinition(h,value);await h.node();assert.equal(h.fields.some(f=>f.name==='mode'&&f.value==='ai'),false);h.field('job_guidance','기존 AI 안내 수정');h.click('save');await flush();assert.equal(h.writes[0].definition.nodes.j.result_source_job_id,'cr-list');assert.deepEqual(h.writes[0].definition.nodes.j.effect_criterion,value.nodes.j.effect_criterion);});

test('confirmed list bindings and hidden deadline rules preserve declared references on save',async()=>{
 const h=harness(),tool=c66LegacyTool(h,{properties:{issue_keys:{type:'array'}}}),value=definition();Object.assign(value.nodes.j,{mode:'tool',tool_contract_id:tool.id,tool_reference:copy(tool.reference),deps:['confirmed-list'],inputs:[{id:'deployment',name:'배포일',type:'datetime',scope:'run'}],argument_bindings:{issue_keys:{result:{job_id:'confirmed-list',path:['items'],value_field:'id',confirmed:true}}},deadline:{input:'deployment',offset_days:-2,timezone:'Asia/Seoul',calendar:'business'}});value.nodes['confirmed-list']={...copy(value.nodes.j),id:'confirmed-list',name:'확정 목록',result_block:'list_confirm',deps:[]};value.nodes.t.children.unshift('confirmed-list');installDefinition(h,value);await h.node();await a12Open(h);assert.match(h.modalMarkup,/앞 작업 결과 연결을 유지/);await h.modalClose('apply');h.field('job_guidance','안내 변경');h.click('save');await flush();const node=h.writes[0].definition.nodes.j;assert.deepEqual(node.argument_bindings,value.nodes.j.argument_bindings);assert.deepEqual(node.deadline,value.nodes.j.deadline);assert.equal(node.due_at,undefined);
});

test('a stored AI report keeps resolved-verdict dependency separate from human completion',async()=>{const h=harness(),value=definition();Object.assign(value.nodes.j,{mode:'ai',result_block:'ai_review',dependency_policy:'all_resolved'});installDefinition(h,value);await h.node();h.field('job_guidance','보고 안내만 수정');h.click('save');await flush();assert.equal(h.writes[0].definition.nodes.j.dependency_policy,'all_resolved');assert.equal(h.writes[0].definition.nodes.j.human_confirmation,true);});

test('factory settings fetch dynamic choices from the saved definition and never substitute examples after failure',async()=>{const h=harness();h.workflows.get('w').draft.nodes.j.inputs=[{id:'project',name:'실제 프로젝트',type:'single',scope:'workflow',options_source:'tool',options_query:{reference:{tool_id:'jira',function:'jira_project_metadata',content_hash:'x'},argument_bindings:{project_key:{constant:''}},result_path:['projects'],value_field:'id',label_field:'name'}}];h.render();const queries=[];h.callbacks.options=async body=>{queries.push(copy(body));return {ok:true,options:[{id:'APPX',name:'실제 프로젝트 표시'}]};};h.dialogs.push({'override:project':true,'value:project':'APPX'});h.click('factory_settings');await flush();assert.equal(queries[0].job_id,'j');assert.equal(queries[0].workflow_id,'w');assert.match(h.dialogHistory.at(-1).html,/실제 프로젝트 표시/);assert.deepEqual(h.writes.at(-1).values,{project:'APPX'});h.callbacks.options=async()=>{throw new Error('현재 권한 없음');};h.dialogs.push({'override:project':true,'value:project':'EMS'});const before=h.writes.length;h.click('factory_settings');await flush();assert.equal(h.writes.length,before);assert.match(h.markup,/현재 선택지를 확인한 뒤/);});
test('person settings use current Native people metadata without making free-text users',async()=>{const h=harness();h.workflows.get('w').draft.nodes.j.inputs=[{id:'reviewer',name:'검토자',type:'person',scope:'workflow'}];h.state.people=[{id:'a',name:'실제 사용자',value:{kind:'user',id:'a'}},{id:'g',name:'실제 그룹',value:{kind:'group',id:'g'}}];h.render();h.dialogs.push({'override:reviewer':true,'value:reviewer':'group:g'});h.click('factory_settings');await flush();assert.match(h.dialogHistory.at(-1).html,/실제 사용자/);assert.match(h.dialogHistory.at(-1).html,/실제 그룹/);assert.deepEqual(h.writes.at(-1).values,{reviewer:{kind:'group',id:'g'}});});

test('Native proposal review is visibly open from a selected job and non-structure tabs without saving',async()=>{for(const view of ['job','history','schedule','rules']){const h=harness();if(view==='job')await h.node();else{h.click('tab',{tab:view});await flush();}const proposal={workflow_id:'w',base_revision:1,context_id:'native-context',definition:{...definition(),name:'대화 제안'}};h.designer.acceptProposal(proposal,{chatId:'private-chat'});assert.match(h.markup,/업무 도우미 수정 제안/);assert.doesNotMatch(h.markup,/<pre|<details class="ew-author-ai"/);assert.equal(h.buttons.filter(b=>b.dataset.authorAction==='ai_apply').length,1);assert.equal(h.buttons.filter(b=>b.dataset.authorAction==='ai_discard').length,1);if(view==='job')assert.match(h.markup,/id="ew-author-node"/);assert.equal(h.draft().definition.name,'절차 w');assert.equal(h.writes.length,0);h.click('ai_apply');await flush();assert.equal(h.draft().definition.name,'대화 제안');assert.equal(h.draft().dirty,true);assert.equal(h.writes.length,0);}});
test('job assignee uses only current Native user/group identities and persists exact principal',async()=>{const h=harness();h.state.people=[{id:'u',name:'현재 사용자',value:{kind:'user',id:'u'}},{id:'g',name:'현재 그룹',value:{kind:'group',id:'g'}}];h.render();await h.node();assert.match(h.markup,/현재 사용자/);assert.match(h.markup,/현재 그룹/);h.field('assignee','group:g','change');h.click('save');await flush();assert.deepEqual(h.writes[0].definition.nodes.j.assignee,{kind:'group',id:'g'});h.field('assignee','user:invented','change');assert.deepEqual(h.draft().definition.nodes.j.assignee,{kind:'group',id:'g'});h.field('assignee','','change');assert.equal(h.draft().definition.nodes.j.assignee,undefined);});
test('unavailable existing assignee is preserved on unrelated edits and removed only explicitly',async()=>{const h=harness();h.workflows.get('w').draft.nodes.j.assignee={kind:'user',id:'opaque-prior-user'};h.render();await h.node();assert.match(h.markup,/기존 담당자 · 현재 접근 확인 필요/);h.field('job_guidance','안내 수정');assert.deepEqual(h.draft().definition.nodes.j.assignee,{kind:'user',id:'opaque-prior-user'});h.field('assignee','','change');assert.equal(h.draft().definition.nodes.j.assignee,undefined);});
test('B5 explicitly authored output contract saves an object while Native input schema stays authoritative',async()=>{const h=harness(),schema={type:'object',properties:{ticket:{type:'string'},status:{type:'string'}},required:['ticket']};h.selection.tab='tools';h.state.native_functions=[{name:'Registered request',kind:'request',reference:{tool_id:'current',function:'request',content_hash:'actual'},schema:{type:'object',properties:{target:{type:'string'}}}}];h.render();await h.pick('current:request');h.field('output_schema_json',JSON.stringify(schema));h.field('guide_url','https://example.invalid/verified-guide');h.click('tool_save');await flush();assert.deepEqual(h.operations[0].tool.output_schema,schema);assert.deepEqual(h.operations[0].tool.input_schema,{type:'object',properties:{target:{type:'string'}}});assert.equal(h.operations[0].tool.output_schema_json,undefined);assert.match(h.markup,/가이드 문서/);assert.match(h.markup,/필수/);assert.doesNotMatch(h.markup,/name="input_schema/);});
test('invalid output contract remains editable and cannot save or submit stale schema',async()=>{for(const invalid of ['{bad json','[]','null','"schema"']){const h=harness();h.selection.tab='tools';h.state.tools=[{id:'tool',name:'요청',kind:'request',revision:3,state:'draft',output_schema:{type:'object'}}];h.render();h.click('tool_open',{id:'tool'});await flush();h.field('output_schema_json',invalid);h.click('tool_save');await flush();assert.equal(h.operations.length,0);assert.equal(h.fields.find(f=>f.name==='output_schema_json').value,invalid);assert.match(h.markup,/올바른 JSON Schema 객체/);h.click('tool_review');await flush();assert.equal(h.operations.length,0);h.field('output_schema_json','{"type":"object"}');h.click('tool_save');await flush();assert.deepEqual(h.operations[0].tool.output_schema,{type:'object'});}});
test('existing output contract is not silently replaced by metadata when unrelated fields change',async()=>{const h=harness(),reference={tool_id:'current',function:'read'},saved={type:'object',properties:{reviewed:{type:'boolean'}}};h.selection.tab='tools';h.state.tools=[{id:'tool',name:'조회',kind:'read',revision:4,state:'draft',reference,output_schema:saved}];h.state.native_functions=[{name:'조회',kind:'read',reference,schema:{type:'object'},output_schema:{type:'object',properties:{different:{type:'string'}}}}];h.render();h.click('tool_open',{id:'tool'});await flush();h.field('description','안내만 수정');h.click('tool_save');await flush();assert.deepEqual(h.operations[0].tool.output_schema,saved);});
test('input deletion requires confirmation and retains dangling bindings for publish validation',async()=>{const h=harness(),node=h.workflows.get('w').draft.nodes.j;node.inputs=[{id:'date',name:'기준 날짜',type:'datetime',scope:'run'}];node.argument_bindings={target:{input:'date'}};node.deadline={input:'date',offset_days:-1,timezone:'Asia/Seoul',calendar:'calendar'};h.render();await h.node();h.dialogs.push(null);h.click('input_delete',{id:'date'});await flush();assert.equal(h.draft().definition.nodes.j.inputs.length,1);h.dialogs.push({});h.click('input_delete',{id:'date'});await flush();assert.deepEqual(h.draft().definition.nodes.j.inputs,[]);assert.deepEqual(h.draft().definition.nodes.j.argument_bindings,{target:{input:'date'}});assert.equal(h.draft().definition.nodes.j.deadline.input,'date');assert.equal(h.writes.length,0);});
test('input deletion confirmation cannot mutate a different workflow after navigation',async()=>{const h=harness();h.workflows.get('w').draft.nodes.j.inputs=[{id:'field',name:'입력',type:'text'}];h.render();await h.node();h.dialogs.push({});h.dialogHook=()=>h.open('q');h.click('input_delete',{id:'field'});await flush();await h.open('w');assert.equal(h.draft().definition.nodes.j.inputs.length,1);assert.equal(h.writes.length,0);});
test('version history displays the exact stored publisher safely',async()=>{const h=harness();h.workflows.get('w').versions=[{version:1,publisher:'user:<native-id>',published_at:'2026-10-02',hash:'saved-hash'}];h.render();h.click('tab',{tab:'history'});await flush();assert.match(h.markup,/user:&lt;native-id&gt;/);assert.doesNotMatch(h.markup,/<native-id>/);});

test('Native proposal keeps direct draft unchanged across workspace repaints',async()=>{const h=harness();h.proposal({...definition(),name:'검토 중 제안'});for(let i=0;i<3;i++)h.render();assert.match(h.markup,/업무 도우미 수정 제안/);assert.equal(h.draft().definition.name,'절차 w');assert.equal(h.draft().dirty,false);assert.equal(h.writes.length,0);h.click('ai_apply');await flush();assert.equal(h.draft().definition.name,'검토 중 제안');assert.equal(h.draft().dirty,true);});

test('discarding a Native proposal is explicit and workspace polls do not restore it',async()=>{const h=harness();h.proposal({...definition(),name:'버릴 제안'});h.click('ai_discard');await flush();for(let i=0;i<3;i++)h.render();assert.equal(h.buttons.some(button=>button.dataset.authorAction==='ai_apply'),false);assert.equal(h.draft().definition.name,'절차 w');assert.equal(h.draft().dirty,false);assert.equal(h.writes.length,0);});

test('Native proposal previews stay private to workflow conversation and account',async()=>{for(const change of ['workflow','conversation','account']){const h=harness();h.proposal({...definition(),name:'A 비공개 제안'});if(change==='workflow')await h.open('q');else{if(change==='conversation')h.selection.chat_id='other-private-chat';else h.state.capabilities.actor_id='b';h.render();}assert.equal(h.buttons.some(button=>button.dataset.authorAction==='ai_apply'),false);assert.doesNotMatch(h.markup,/A 비공개 제안/);assert.equal(h.writes.length,0);}});

test('a late Native proposal is rejected after a conversation switch',async()=>{const h=harness(),pending=deferred();const delivery=pending.promise.then(value=>h.designer.acceptProposal(value,{chatId:'private-chat'}));h.selection.chat_id='different-chat';h.render();pending.resolve({workflow_id:'w',base_revision:1,context_id:'old-chat',definition:{...definition(),name:'이전 대화 응답'}});await assert.rejects(delivery);assert.equal(h.buttons.some(button=>button.dataset.authorAction==='ai_apply'),false);assert.doesNotMatch(h.markup,/이전 대화 응답/);assert.equal(h.draft().definition.name,'절차 w');assert.equal(h.writes.length,0);});

test('B2-2 rules are scoped to eligible jobs and preserve stored judgment IDs and legacy defaults',async()=>{
 const h=harness(),record=h.workflows.get('w'),global=[{id:'approved-old',label:'통과',status:'completed'}];record.draft.judgments=global;
 record.draft.nodes.j.result_block='item_verdict';record.draft.nodes.k={...copy(record.draft.nodes.j),id:'k',name:'별도 판정',result_block:'checklist'};
 h.render();h.click('tab',{tab:'rules'});await flush();assert.equal(h.draft().dirty,false);assert.equal(h.draft().definition.nodes.j.judgments,undefined);
 assert.match(h.markup,/확인 항목·항목별 판정/);assert.doesNotMatch(h.markup,/CR별 승인|개발 설계서|조건부 승인/);
 h.dialogs.push({label:'확인 완료',status:'completed',consequence:'다음 작업에서 근거 확인'});h.click('judgment_edit',{id:'0'});await flush();
 assert.deepEqual(h.draft().definition.nodes.j.judgments,[{id:'approved-old',label:'확인 완료',status:'completed',consequence:'다음 작업에서 근거 확인'}]);
 assert.deepEqual(h.draft().definition.judgments,global);assert.equal(h.draft().definition.nodes.k.judgments,undefined);
 h.field('rule_job_id','k','change');h.dialogs.push({label:'보완 필요',status:'action_required',consequence:'담당자 확인'});h.click('judgment_add');await flush();
 const k=h.draft().definition.nodes.k;assert.equal(k.judgments.length,2);assert.equal(k.judgments[0].id,'approved-old');assert.equal(h.draft().definition.nodes.j.judgments.length,1);
 assert.equal(h.writes.length,0);h.click('save');await flush();assert.equal(h.writes[0].definition.nodes.k.judgments[1].label,'보완 필요');
});
test('B2-2 suggestion rules save guidance and human-only IDs without auto-confirmation or reference replacement',async()=>{
 const h=harness(),record=h.workflows.get('w');record.draft.nodes.j.result_block='item_verdict';record.draft.nodes.j.judgments=[{id:'ok',label:'승인',status:'completed'},{id:'human',label:'보완 후 확인',status:'action_required'}];record.draft.nodes.j.suggestion_rules={description:'기존 제안 기준',provisional:true,rules:[],human_only_judgment_ids:[]};
 h.render();h.click('tab',{tab:'rules'});await flush();h.field('suggestion_description','현재 입력에서 확인한 필수 조건');h.field('human_only:human',true,'change');
 h.dialogs.push({condition:'근거가 충분하지 않으면',judgment_id:''});h.click('suggestion_add');await flush();
 h.dialogs.push({condition:'근거가 충족되면',judgment_id:'ok'});h.click('suggestion_add');await flush();
 const node=h.draft().definition.nodes.j;assert.equal(node.suggestion_rules.provisional,true);assert.deepEqual(node.suggestion_rules.human_only_judgment_ids,['human']);
 assert.deepEqual(node.suggestion_rules.rules.map(rule=>[rule.condition,rule.outcome,rule.judgment_id]),[['근거가 충분하지 않으면','none',''],['근거가 충족되면','judgment','ok']]);
 assert.doesNotMatch(h.dialogHistory.at(-1).html,/<option value="human"/);assert.equal(node.human_confirmation,true);assert.equal(h.writes.length,0);
 h.field('confirmation_notes','확정 뒤에는 근거를 다시 확인');h.click('save');await flush();assert.equal(h.writes[0].definition.nodes.j.confirmation_notes,'확정 뒤에는 근거를 다시 확인');
});
test('B2-2 a job switch while its dialog is open cannot edit a different job',async()=>{
 const h=harness(),record=h.workflows.get('w');record.draft.nodes.j.result_block='checklist';record.draft.nodes.k={...copy(record.draft.nodes.j),id:'k',name:'다른 작업'};
 h.render();h.click('tab',{tab:'rules'});await flush();h.dialogs.push({label:'이전 화면의 변경',status:'failed'});h.dialogHook=()=>h.field('rule_job_id','k','change');h.click('judgment_add');await flush();
 assert.equal(h.draft().definition.nodes.j.judgments,undefined);assert.equal(h.draft().definition.nodes.k.judgments,undefined);assert.equal(h.draft().dirty,false);
});
test('B2-3 advisories do not block publication while blockers remain visible and disabled',async()=>{
 const h=harness(),record=h.workflows.get('w');h.writeOverride=async body=>{if(body.action==='validate_workflow'){record.validation={revision:1,checked_at:'2026-10-05T08:00:00Z',errors:[],warnings:['j: 송부 방식이 정해지지 않았습니다'],checks:['결과 형태 확인']};return {ok:true,validation:copy(record.validation)};}return {ok:true};};
 h.click('validate');await flush();assert.match(h.markup,/게시를 막는 문제 0/);assert.match(h.markup,/확인 권장 1/);assert.match(h.markup,/통과 1/);assert.match(h.markup,/2026-10-05T08:00:00Z/);assert.equal(h.buttons.find(button=>button.dataset.authorAction==='publish').disabled,false);
 h.click('validation_open',{id:'warnings:0'});await flush();assert.match(h.markup,/ew-author-rule-policy/);
 h.writeOverride=async()=>{record.validation={revision:1,errors:['j: 결과 형태 없음'],warnings:[],checks:[]};return {ok:true,validation:copy(record.validation)};};h.click('validate');await flush();assert.match(h.markup,/게시를 막는 문제 1/);assert.equal(h.buttons.find(button=>button.dataset.authorAction==='publish').disabled,true);
 h.click('publish');await flush();assert.equal(h.writes.filter(body=>body.action==='publish_workflow').length,0);h.click('validation_open',{id:'errors:0'});await flush();assert.match(h.markup,/id="ew-author-node"/);
});
test('B5 direct execution stores only declared exception metadata and retains absent adapter reason',async()=>{
 const h=harness();h.selection.tab='tools';h.state.native_users=[{id:'owner',name:'시스템 담당자'}];h.state.reviewers=[{id:'owner',name:'시스템 담당자'}];h.state.can_author_direct=true;h.render();await h.example('restart-service');h.click('tool_direct');await flush();
 assert.match(h.markup,/직접 실행 · 예외/);assert.match(h.markup,/실행 주체는 EES Workflow/);assert.match(h.markup,/허용된 실행 연결이 없으면 실제 동작은 차단/);
 h.field('name','담당자 소유 예외');h.field('exception:api_unavailable_reason','담당자 검토에서 API 제공 불가 확인');h.field('exception:owner_user_id','owner','change');h.field('exception:allowed_commands','approved-command-1\napproved-command-2');h.field('exception:account_reference','dedicated-account');h.field('exception:least_privilege',true,'change');h.field('responsible_user_id','owner','change');h.click('tool_save');await flush();
 const tool=h.operations[0].tool;assert.equal(tool.kind,'direct');assert.deepEqual(tool.exception_contract,{api_unavailable_reason:'담당자 검토에서 API 제공 불가 확인',owner_user_id:'owner',allowed_commands:['approved-command-1','approved-command-2'],account_reference:'dedicated-account',least_privilege:true});assert.equal(Object.keys(tool).some(key=>key.startsWith('exception:')),false);assert.equal(tool.reference,undefined);assert.equal(h.operations.some(body=>body.action.includes('execute')),false);
});
test('C12 schedule opening and explicit execution scope do not alter preserved drafts on inspection',async()=>{
 const h=harness();h.workflows.get('w').draft.nodes.j.execution_scope='opaque-user-value';h.render();await h.node();assert.doesNotMatch(h.markup,/name="execution_scope"/);assert.equal(h.draft().definition.execution_scope,undefined);h.click('edit_workflow');await flush();h.field('execution_scope','system');h.click('summary_apply');await flush();assert.equal(h.draft().definition.execution_scope,'system');assert.equal(h.draft().definition.nodes.j.execution_scope,'opaque-user-value');h.click('edit_workflow');await flush();h.field('execution_scope','');h.click('summary_apply');await flush();assert.equal(h.draft().definition.execution_scope,undefined);
 h.click('tab',{tab:'schedule'});h.click('run_mode',{id:'periodic'});await flush();assert.match(h.markup,/직전 회차가 남아도 일정대로 열림/);h.field('opening','on_schedule','change');assert.equal(h.draft().definition.schedule.opening,'on_schedule');
});

test('B5 direct classification selects registered Native metadata without configuring execution',async()=>{
 const h=harness(),reference={tool_id:'registered',function:'permitted',content_hash:'current'},schema={type:'object',properties:{target:{type:'string'}}};h.selection.tab='tools';h.state.can_author_direct=true;h.state.native_functions=[{kind:'request',name:'등록 기능',reference,schema},nativeFunction('registered','상태 조회','request','observed_status')];h.render();await h.pick('registered:permitted');h.click('tool_direct');await flush();h.field('status_function','observed_status','change');h.click('tool_save');await flush();const tool=h.operations[0].tool;assert.equal(tool.kind,'direct');assert.deepEqual(tool.reference,reference);assert.deepEqual(tool.input_schema,schema);assert.equal(tool.status_function,'observed_status');assert.match(h.markup,/기능을 선택해도 직접 실행 연결은 구성되지 않습니다/);assert.doesNotMatch(h.markup,/name="input_schema/);
});


// Simulate the missing API on intranet HTTP; these remain synthetic DOM tests.
const uuidV4=/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const httpCrypto=()=>({getRandomValues:bytes=>crypto.webcrypto.getRandomValues(bytes)});
test('missing randomUUID permits create and authoring IDs through the shared helper',async()=>{
 const h=harness({cryptoProvider:httpCrypto()});await flush();
 await beginCreation(h,'HTTP 새 절차');await submitCreation(h);h.click('tab',{tab:'content'});assert.equal(h.writes[0].action,'create_workflow');assert.match(h.writes[0].request_id,uuidV4);
 assert.equal(h.writes[0].name,'HTTP 새 절차');assert.equal(h.writes[0].expected_revision,0);
 h.click('add_stage');await flush();await h.inline('추가 단계');const stage=Object.values(h.draft().definition.nodes).find(node=>node.id.startsWith('stage-'));
 assert.match(stage.id.slice(6),uuidV4);h.click('add_job',{parent:stage.id});await flush();await h.inline('추가 작업');
 const job=Object.values(h.draft().definition.nodes).find(node=>node.id.startsWith('job-'));assert.match(job.id.slice(4),uuidV4);
 const answer={name:'대상 서버',type:'text',scope:'run',options_source:'manual'};
 h.dialogHook=()=>{answer.id=controls(h.dialogHistory.at(-1).html).find(field=>field.name==='id').value;};
 h.dialogs.push(answer);h.click('input_add');await flush();h.dialogHook=null;
 const field=h.draft().definition.nodes[job.id].inputs[0];assert.match(field.id.slice(6),uuidV4);
 h.field('result_block','item_verdict','change');h.click('tab',{tab:'rules'});await flush();
 h.dialogs.push({label:'확인 완료',status:'completed',consequence:'근거 확인'});h.click('judgment_add');await flush();
 const judgment=h.draft().definition.nodes[job.id].judgments.find(value=>value.id.startsWith('judgment-'));assert.match(judgment.id.slice(9),uuidV4);
 h.dialogs.push({condition:'근거가 확인되면',judgment_id:judgment.id});h.click('suggestion_add');await flush();
 const rule=h.draft().definition.nodes[job.id].suggestion_rules.rules[0];assert.match(rule.id.slice(5),uuidV4);
 h.click('save');await flush();const saved=h.writes.at(-1);assert.equal(saved.action,'save_draft');assert.match(saved.request_id,uuidV4);
 assert.equal(saved.definition.nodes[job.id].parent,stage.id);assert.equal(saved.definition.nodes[job.id].inputs[0].id,field.id);
 assert.equal(saved.definition.nodes[job.id].suggestion_rules.rules[0].judgment_id,judgment.id);
 const ids=[h.writes[0].request_id,stage.id.slice(6),job.id.slice(4),field.id.slice(6),judgment.id.slice(9),rule.id.slice(5),saved.request_id];
 assert.equal(new Set(ids).size,ids.length);assert.equal(h.workflows.get('w').published_version,null);
});
test('missing randomUUID keeps authoring retries idempotent and changed edits distinct',async()=>{
 const h=harness({cryptoProvider:httpCrypto()});await h.node();h.writeOverride=async()=>{throw new Error('response lost');};
 h.field('job_guidance','재시도할 초안');h.click('save');await flush();h.click('save');await flush();
 assert.match(h.writes[0].request_id,uuidV4);assert.deepEqual(h.writes[1],h.writes[0]);
 h.field('job_guidance','바뀐 초안');h.click('save');await flush();assert.match(h.writes[2].request_id,uuidV4);
 assert.notEqual(h.writes[2].request_id,h.writes[0].request_id);assert.equal(h.draft().definition.nodes.j.instructions,'바뀐 초안');
});
test('missing randomUUID keeps AI proposal context and explicit apply without saving',async()=>{
 const h=harness({cryptoProvider:httpCrypto()});await flush();const contextId=run(renderer({crypto:httpCrypto()}),'workUI.newId()');assert.match(contextId,uuidV4);
 h.proposal({...definition(),name:'AI 제안'},{context_id:contextId});assert.equal(h.proposals.length,0);
 assert.equal(h.draft().definition.name,'절차 w');assert.equal(h.writes.length,0);
 h.click('ai_apply');await flush();assert.equal(h.draft().definition.name,'AI 제안');assert.equal(h.draft().dirty,true);assert.equal(h.writes.length,0);
});

test('easy tool starter groups live connections and searches names without creating a contract',async()=>{
 const h=harness();h.selection.tab='tools';h.state.native_functions=[nativeFunction('jira','CR 승인 상태 조회','read','jira_search_crs'),nativeFunction('jira','프로젝트 조회','read','jira_project_metadata'),nativeFunction('ops','재시작 요청','request','restart_service')];h.render();h.click('tool_create');await flush();
 assert.match(h.markup,/예시에서 시작/);assert.match(h.markup,/연결된 기능에서 고르기/);assert.match(h.markup,/연결된 Jira/);assert.match(h.markup,/jira:jira_search_crs/);assert.match(h.markup,/정보 읽기/);assert.match(h.markup,/EES에 작업 부탁/);
 assert.equal(h.buttons.filter(button=>button.dataset.authorAction==='tool_example').length,4);assert.equal(h.buttons.filter(button=>button.dataset.authorAction==='tool_pick').length,3);assert.equal(h.fields.some(field=>field.name==='name'),false);assert.equal(h.operations.length,0);
 h.field('ew-tool-search','승인');await flush();assert.deepEqual(h.buttons.filter(button=>button.dataset.authorAction==='tool_pick').map(button=>button.dataset.id),['jira:jira_search_crs']);assert.equal(h.operations.length,0);
});
test('tool examples resolve current connections anew and EMS read examples remain unconnected',async()=>{
 const h=harness();h.selection.tab='tools';h.state.native_functions=[nativeFunction('jira','CR 조회','read','jira_search_crs'),nativeFunction('ems','상태 조회','request','service_status')];h.render();await h.example('jira-query');h.click('tool_save');await flush();
 assert.equal(h.operations[0].tool.name,'Jira 조회');assert.equal(h.operations[0].tool.kind,'read');assert.deepEqual(h.operations[0].tool.reference,h.state.native_functions[0].reference);assert.equal(h.operations[0].tool.id,undefined);
 h.click('tool_list');await flush();h.state.native_functions=[];h.render();await h.example('jira-query');h.click('tool_save');await flush();assert.equal(h.operations[1].tool.reference,undefined);assert.equal(h.operations[1].tool.id,undefined);assert.equal(h.buttons.find(button=>button.dataset.authorAction==='tool_review').disabled,true);assert.match(h.markup,/필요한 기능이 아직 연결되지 않았습니다/);h.click('tool_review');await flush();assert.equal(h.operations.length,2);
 h.click('tool_list');await flush();h.state.native_functions=[nativeFunction('ems','상태 조회','read','service_status')];h.render();await h.example('service-status');h.click('tool_save');await flush();assert.equal(h.operations[2].tool.reference,undefined);assert.equal(h.operations[2].tool.kind,'read');assert.match(h.markup,/필요한 기능이 아직 연결되지 않았습니다/);assert.equal(h.writes.length,0);
});
test('choosing a live function determines kind and new output contracts are never fabricated',async()=>{
 for(const kind of ['read','request']){const h=harness();h.selection.tab='tools';h.state.native_functions=[nativeFunction('registered','현재 기능',kind,'current')];h.render();await h.pick('registered:current');assert.equal(h.fields.some(field=>field.name==='kind'),false);assert.equal(h.fields.find(field=>field.name==='output_schema_json').value,'');assert.match(h.markup,/고급 · 개발자용/);assert.doesNotMatch(h.markup,/<details[^>]*open[^>]*>[\s\S]*결과 형식/);h.click('tool_save');await flush();assert.equal(h.operations[0].tool.kind,kind);assert.equal(h.operations[0].tool.output_schema,undefined);}
});
test('removed time fields remain opaque and survive unrelated read and request resaves',async()=>{
 for(const kind of ['read','request']){const h=harness(),fn=nativeFunction('registered','현재 기능',kind,'current');h.selection.tab='tools';h.state.native_functions=[fn];h.state.tools=[{id:'legacy',name:'기존 도구',kind,reference:fn.reference,input_schema:fn.schema,revision:9,state:'draft',timeout_seconds:37,completion_wait_seconds:642,output_schema:{type:'object',properties:{kept:{type:'string'}}}}];h.render();h.click('tool_open',{id:'legacy'});await flush();assert.equal(h.fields.some(field=>['timeout_seconds','completion_wait_seconds','kind'].includes(field.name)),false);h.field('description','설명만 수정');h.click('tool_save');await flush();assert.equal(h.operations[0].tool.timeout_seconds,37);assert.equal(h.operations[0].tool.completion_wait_seconds,642);assert.equal(h.operations[0].expected_revision,9);assert.deepEqual(h.operations[0].tool.output_schema,{type:'object',properties:{kept:{type:'string'}}});}
});
test('request state choices stay within the connected tool and sole reviewer and state function are preselected',async()=>{
 const h=harness();h.selection.tab='tools';h.state.reviewers=[{id:'owner',name:'EES 담당자'}];h.state.native_functions=[nativeFunction('ops','재시작','request','restart_service'),nativeFunction('ops','재시작 상태','request','restart_status'),nativeFunction('unrelated','다른 상태','request','other_status')];h.render();await h.pick('ops:restart_service');assert.equal(h.fields.find(field=>field.name==='status_function').value,'restart_status');assert.doesNotMatch(h.markup,/<option value="other_status"/);assert.doesNotMatch(h.markup,/<option value="restart_service"/);h.click('tool_save');await flush();assert.equal(h.operations[0].tool.status_function,'restart_status');assert.equal(h.operations[0].tool.responsible_user_id,'owner');assert.equal(h.operations[0].tool.output_schema,undefined);assert.equal(h.buttons.find(button=>button.dataset.authorAction==='tool_review').disabled,true);h.field('guide_url','https://example.invalid/guide');h.click('tool_save');await flush();assert.match(h.markup,/결과 형식이 비어 있습니다/);assert.match(h.markup,/담당자나 개발자/);h.click('tool_review');await flush();assert.equal(h.operations.length,2);
});
test('multiple request state functions and reviewers require a choice and changing a function preserves authored text',async()=>{
 const h=harness();h.selection.tab='tools';h.state.reviewers=[{id:'first',name:'첫 담당자'},{id:'second',name:'둘째 담당자'}];h.state.native_functions=[nativeFunction('ops','재시작','request','restart_service'),nativeFunction('ops','상태1','request','status_one'),nativeFunction('ops','상태2','request','status_two'),nativeFunction('jira','CR 조회','read','jira_search_crs')];h.render();await h.pick('ops:restart_service');assert.equal(h.fields.find(field=>field.name==='status_function').value,'');assert.equal(h.fields.find(field=>field.name==='responsible_user_id').value,'');h.field('name','내가 쓴 도구');h.field('description','내가 쓴 설명');h.click('tool_change');await flush();h.click('tool_pick',{id:'jira:jira_search_crs'});await flush();h.click('tool_save');await flush();assert.equal(h.operations[0].tool.kind,'read');assert.equal(h.operations[0].tool.name,'내가 쓴 도구');assert.equal(h.operations[0].tool.description,'내가 쓴 설명');assert.equal(h.operations[0].tool.status_function,undefined);assert.equal(h.fields.some(field=>field.name==='responsible_user_id'),false);
});
test('read confirmation is allowed after save without a guide and explicit next step clears when complete',async()=>{
 const h=harness();h.selection.tab='tools';h.state.native_functions=[nativeFunction('jira','CR 조회','read','jira_search_crs')];h.render();await h.pick('jira:jira_search_crs');assert.match(h.markup,/초안을 먼저 저장/);assert.equal(h.fields.some(field=>field.name==='responsible_user_id'),false);h.click('tool_save');await flush();assert.equal(h.buttons.find(button=>button.dataset.authorAction==='tool_review').disabled,false);h.click('tool_review');await flush();assert.equal(h.operations.at(-1).action,'tool_submit');assert.equal(h.operations.at(-1).tool_contract_id,'tool');assert.equal(h.operations[0].tool.guide_url || '','');
});
test('direct exception creation is hidden and inert without an eligible reviewer capability',async()=>{
 for(const allowed of [false,true]){const h=harness();h.selection.tab='tools';h.state.can_author_direct=allowed;h.render();await h.example('restart-service');assert.equal(h.buttons.some(button=>button.dataset.authorAction==='tool_direct'),allowed);h.click('tool_direct');await flush();if(allowed){assert.match(h.markup,/직접 실행 · 예외/);assert.ok(h.fields.some(field=>field.name==='exception:api_unavailable_reason'));}else{assert.equal(h.fields.some(field=>field.name==='exception:api_unavailable_reason'),false);assert.equal(h.operations.length,0);}}
});
test('unconnected examples still save with missing randomUUID but never submit or execute',async()=>{
 const h=harness({cryptoProvider:httpCrypto()});h.selection.tab='tools';h.render();await h.example('collection-queue');h.click('tool_save');await flush();assert.match(h.operations[0].request_id,uuidV4);assert.equal(h.operations[0].tool.kind,'read');assert.equal(h.operations[0].tool.reference,undefined);h.click('tool_review');await flush();assert.equal(h.operations.length,1);assert.match(h.markup,/필요한 기능이 아직 연결되지 않았습니다/);
});


test('tool drafts are private to actor and system and return without crossing the selected system',async()=>{
 const h=harness();h.selection.tab='tools';h.render();await h.example('jira-query');h.field('name','EMS 개인 도구');h.field('description','EMS에 남길 개인 초안');
 h.selection.system_id='MES';h.render();assert.doesNotMatch(h.markup,/EMS 개인 도구|EMS에 남길 개인 초안/);await h.example('restart-service');h.field('name','MES 개인 도구');h.field('description','MES에 남길 개인 초안');
 h.selection.system_id='EMS';h.render();assert.equal(h.fields.find(field=>field.name==='name').value,'EMS 개인 도구');assert.equal(h.fields.find(field=>field.name==='description').value,'EMS에 남길 개인 초안');h.click('tool_save');await flush();assert.equal(h.operations[0].tool.system_id,'EMS');assert.equal(h.operations[0].tool.name,'EMS 개인 도구');
 h.state.capabilities.actor_id='different-user';h.render();assert.doesNotMatch(h.markup,/EMS 개인 도구|MES 개인 도구|개인 초안/);h.selection.system_id='MES';h.render();assert.doesNotMatch(h.markup,/EMS 개인 도구|MES 개인 도구|개인 초안/);
});
test('Native navigation waits for a real authoring save or load while preserving the draft',async()=>{
 const h=harness(),saving=deferred();await h.node();h.field('job_guidance','Native 화면에 다녀와도 남길 초안');h.writeOverride=()=>saving.promise;
 assert.equal(h.designer.canNavigate(),true);h.click('save');await flush();assert.equal(h.designer.canNavigate(),false);assert.equal(h.draft().definition.nodes.j.instructions,'Native 화면에 다녀와도 남길 초안');
 saving.resolve({ok:true,revision:2});await flush();assert.equal(h.designer.canNavigate(),true);
 const loading=deferred();h.readOverride=()=>loading.promise;const pending=h.designer.load();assert.equal(h.designer.canNavigate(),false);loading.resolve({workflow:copy(h.workflows.get('w')),capabilities:copy(h.state.capabilities)});await pending;assert.equal(h.designer.canNavigate(),true);
});
test('tool save acknowledges its revision and keeps edits typed while the save is pending',async()=>{
 const h=harness(),pending=deferred();h.selection.tab='tools';h.state.native_functions=[nativeFunction('jira','CR 조회','read','jira_search_crs')];h.render();await h.pick('jira:jira_search_crs');h.field('description','보낸 설명');h.operationOverride=()=>pending.promise;h.click('tool_save');await flush();const submitted=h.operations[0];h.field('description','저장 중 새로 입력한 설명');pending.resolve({ok:true,tool:{...submitted.tool,id:'saved-tool',state:'draft',revision:1}});await flush();assert.equal(h.fields.find(field=>field.name==='description').value,'저장 중 새로 입력한 설명');assert.match(h.markup,/저장 안 됨/);assert.equal(h.buttons.find(button=>button.dataset.authorAction==='tool_review').disabled,true);
 h.operationOverride=async body=>({ok:true,tool:{...body.tool,id:'saved-tool',state:'draft',revision:2}});h.click('tool_save');await flush();assert.equal(h.operations[1].expected_revision,1);assert.equal(h.operations[1].tool.id,'saved-tool');assert.equal(h.operations[1].tool.description,'저장 중 새로 입력한 설명');assert.equal(h.operations[0].tool.description,'보낸 설명');
});
test('late tool save cannot replace a different tool opened during the request',async()=>{
 const h=harness(),pending=deferred(),fn=nativeFunction('jira','CR 조회','read','jira_search_crs');h.selection.tab='tools';h.state.native_functions=[fn];h.state.tools=[{id:'first',name:'첫 도구',kind:'read',system_id:'EMS',reference:fn.reference,input_schema:fn.schema,revision:1,state:'draft'},{id:'second',name:'두 번째 도구',kind:'read',system_id:'EMS',reference:fn.reference,input_schema:fn.schema,revision:7,state:'draft'}];h.render();h.click('tool_open',{id:'first'});await flush();h.field('description','첫 도구 저장 요청');h.operationOverride=()=>pending.promise;h.click('tool_save');await flush();const submitted=h.operations[0];h.click('tool_list');h.click('tool_open',{id:'second'});await flush();assert.equal(h.fields.find(field=>field.name==='name').value,'두 번째 도구');pending.resolve({ok:true,tool:{...submitted.tool,revision:2}});await flush();assert.equal(h.fields.find(field=>field.name==='name').value,'두 번째 도구');h.operationOverride=async body=>({ok:true,tool:{...body.tool,revision:8}});h.field('description','다음 도구 수정');h.click('tool_save');await flush();assert.equal(h.operations[1].tool.id,'second');assert.equal(h.operations[1].expected_revision,7);assert.equal(h.operations[1].tool.description,'다음 도구 수정');
});


test('legacy direct metadata survives an ordinary author resave while exception controls remain hidden',async()=>{
 const h=harness(),fn=nativeFunction('legacy','기존 예외 연결','request','execute'),exception={api_unavailable_reason:'검토한 사유',owner_user_id:'owner',allowed_commands:['reviewed-command'],account_reference:'dedicated-account',least_privilege:true};h.selection.tab='tools';h.state.native_functions=[fn];h.state.tools=[{id:'legacy-direct',name:'기존 예외',kind:'direct',system_id:'EMS',state:'draft',revision:4,reference:fn.reference,input_schema:fn.schema,exception_contract:exception}];h.state.can_author_direct=false;h.render();h.click('tool_open',{id:'legacy-direct'});await flush();assert.equal(h.fields.some(field=>field.name.startsWith('exception:')),false);assert.equal(h.buttons.some(button=>['tool_direct','tool_request'].includes(button.dataset.authorAction)),false);h.field('description','설명만 변경');h.click('tool_save');await flush();assert.equal(h.operations[0].tool.kind,'direct');assert.deepEqual(h.operations[0].tool.exception_contract,exception);assert.deepEqual(h.operations[0].tool.reference,fn.reference);
});
test('direct function replacement lists only request functions and rejects a forged read selection',async()=>{
 const h=harness(),current=nativeFunction('ops','기존 예외 연결','request','execute'),next=nativeFunction('new-ops','새 예외 연결','request','execute_next'),read=nativeFunction('jira','조회','read','jira_search_crs');h.selection.tab='tools';h.state.can_author_direct=true;h.state.native_functions=[current,next,read];h.state.tools=[{id:'direct',name:'예외',kind:'direct',system_id:'EMS',state:'draft',revision:5,reference:current.reference,input_schema:current.schema}];h.render();h.click('tool_open',{id:'direct'});await flush();h.click('tool_change');await flush();assert.deepEqual(h.buttons.filter(button=>button.dataset.authorAction==='tool_pick').map(button=>button.dataset.id),['ops:execute','new-ops:execute_next']);h.click('tool_pick',{id:'jira:jira_search_crs'});await flush();assert.match(h.markup,/연결된 기능에서 고르기/);assert.equal(h.operations.length,0);h.click('tool_pick',{id:'new-ops:execute_next'});await flush();h.click('tool_save');await flush();assert.equal(h.operations[0].tool.kind,'direct');assert.deepEqual(h.operations[0].tool.reference,next.reference);assert.deepEqual(h.operations[0].tool.input_schema,next.schema);
});

test('server tool validation errors explain the next action and preserve the editable draft',async()=>{
 for(const [code,message] of [['guide_required',/가이드 문서.*주소를 입력/],['request_output_schema_invalid',/담당자나 개발자/],['native_version_changed',/바꾸기에서 기능을 다시 고르/]]){const h=harness();h.selection.tab='tools';h.state.native_functions=[nativeFunction('jira','CR 조회','read','jira_search_crs')];h.render();await h.pick('jira:jira_search_crs');h.field('description','서버 거부 뒤에도 보존할 설명');h.operationOverride=async()=>({ok:false,error:{code,message:'internal_tool_diagnostic'}});h.click('tool_save');await flush();assert.match(h.markup,message);assert.doesNotMatch(h.markup,/internal_tool_diagnostic/);assert.equal(h.fields.find(field=>field.name==='description').value,'서버 거부 뒤에도 보존할 설명');assert.equal(h.operations.length,1);assert.equal(h.buttons.find(button=>button.dataset.authorAction==='tool_review').disabled,true);}
});

test('new procedure uses the approved inline name and purpose form and cancellation does not create anything',async()=>{
 const h=harness();await beginCreation(h);assert.match(h.markup,/워크플로우 이름|업무 목적/);assert.doesNotMatch(h.markup,/procedure_template|name="(?:category|mode|execution_scope)"/);assert.equal((h.dialogHistory||[]).length,0);h.click('procedure_cancel');await flush();assert.equal(h.writes.length,0);assert.doesNotMatch(h.markup,/기본 제공 절차|예시에서 시작|직접 만들기/);
});
test('named blank creation sends only a name and system and opens content',async()=>{
 const h=harness();await beginCreation(h,'  직접 작성  ');await submitCreation(h);
 assert.equal(h.writes.length,1);assert.equal(h.writes[0].name,'직접 작성');assert.equal(h.writes[0].system_id,'EMS');
 for(const field of ['template_id','definition','description','factory_id','category','mode','execution_scope','schedule'])assert.equal(Object.hasOwn(h.writes[0],field),false,field);
 assert.equal(h.selection.workflow_id,'created-1');assert.match(h.markup,/업무 내용/);assert.match(h.markup,/아직 단계가 없습니다/);assert.doesNotMatch(h.markup,/class="ew-summary-card"/);assert.equal(h.operations.length,0);
});
test('empty or whitespace name never creates a procedure',async()=>{
 for(const name of ['','   ']){const h=harness();await beginCreation(h,name);assert.equal(actionButton(h,'procedure_create').disabled,true);h.designer.handleEvent({type:'submit',target:h.forms['ew-procedure-create']});await flush();assert.equal(h.writes.length,0);assert.match(h.markup,/워크플로우 이름을 입력/);}
});
test('initial procedures use the same list, editor and save command as authored procedures',async()=>{
 const h=harness();h.workflows.get('w').name='신규 공장 횡전개';h.workflows.get('w').draft.name='신규 공장 횡전개';
 await h.open('');assert.match(h.markup,/신규 공장 횡전개/);assert.doesNotMatch(h.markup,/기본 제공 절차|example_open|보기 전용/);
 h.click('open',{id:'w'});await flush();assert.match(h.markup,/신규 공장 횡전개/);assert.match(h.markup,/data-author-action="save"/);
 assert.equal(actionButton(h,'save').disabled,true);await h.node();h.field('job_guidance','기본 제공 절차도 직접 수정');h.click('save');await flush();assert.equal(h.writes[0].action,'save_draft');assert.equal(h.writes[0].workflow_id,'w');assert.equal(h.writes[0].definition.nodes.j.instructions,'기본 제공 절차도 직접 수정');
});
test('failed creation retries the same request while a later successful creation is distinct',async()=>{
 const h=harness({cryptoProvider:httpCrypto()});h.writeOverride=async()=>{throw new Error('응답을 받지 못했습니다');};await beginCreation(h,'반복 생성','보존할 업무 목적');
 for(let attempt=0;attempt<2;attempt++)await submitCreation(h);
 assert.deepEqual(h.writes[0],h.writes[1]);assert.match(h.writes[0].request_id,uuidV4);assert.equal(h.fields.find(field=>field.id==='ew-procedure-description').value,'보존할 업무 목적');
 h.writeOverride=null;await submitCreation(h);assert.equal(h.writes[2].request_id,h.writes[0].request_id);
 await beginCreation(h,'반복 생성');await submitCreation(h);assert.notEqual(h.writes[3].request_id,h.writes[2].request_id);
});
test('system or account changes during inline creation never submit the former context',async()=>{
 for(const change of ['system','actor']){const h=harness();await beginCreation(h,'다른 위치로 보내지 않음','기존 비공개 목적');if(change==='system')h.selection.system_id='APC';else h.state.capabilities.actor_id='another';h.render();assert.equal(h.writes.length,0);assert.doesNotMatch(h.markup,/기존 비공개 목적|다른 위치로 보내지 않음/);}
});
test('late creation response never opens a procedure in a different system',async()=>{
 const h=harness(),pending=deferred();h.writeOverride=()=>pending.promise;await beginCreation(h,'요청 당시 이름','다른 시스템에 보내지 않을 목적');h.click('procedure_create');await flush();assert.equal(h.writes.length,1);
 h.selection.system_id='APC';h.render();pending.resolve({ok:true,workflow_id:'late-created',revision:1});await flush();
 assert.equal(h.selection.system_id,'APC');assert.notEqual(h.selection.workflow_id,'late-created');assert.doesNotMatch(h.markup,/다른 시스템에 보내지 않을 목적/);
});
test('needed information remains direct-editable without a model and publication is explicit',async()=>{
 // C66 removes the needed-information summary. Direct editing and the saved-validation gate remain.
 const h=harness();assert.doesNotMatch(h.markup,/정해야 할 것|data-author-action="summary_open"/);assert.match(h.markup,/게시 전 확인/);
 await h.node();h.field('job_guidance','직접 고침');h.click('validate');await flush();
 assert.equal(actionButton(h,'validate').disabled,true);assert.equal(h.writes.length,0);assert.equal(h.draft().definition.nodes.j.instructions,'직접 고침');
 h.click('publish');await flush();assert.equal(h.writes.length,0);assert.equal(h.modelReads || 0,0);
});
test('removed additional settings preserve stored deadline notes on save',async()=>{const h=harness();h.workflows.get('w').draft.nodes.j.deadline_notes='기존 기한 메모';h.render();await h.node();assert.equal(c66Section(h,'advanced'),undefined);h.field('job_guidance','작업 안내');h.click('save');await flush();assert.equal(h.writes[0].definition.nodes.j.deadline_notes,'기존 기한 메모');assert.equal(h.writes[0].definition.nodes.j.instructions,'작업 안내');});

test('tool field input and change preserve Save and Review controls while reflecting required and dirty state',async()=>{
 const h=harness(),fn=nativeFunction('ops','재시작','request','restart_service'),schema={type:'object',properties:{result:{type:'string'}}};h.selection.tab='tools';h.state.native_functions=[fn,nativeFunction('ops','상태','request','restart_status')];h.state.reviewers=[{id:'reviewer',name:'담당자'}];h.state.tools=[{id:'existing-request',name:'기존 이름',system_id:'EMS',kind:'request',reference:fn.reference,input_schema:fn.schema,status_function:'restart_status',guide_url:'https://example.invalid/guide',output_schema:schema,responsible_user_id:'reviewer',revision:3,state:'draft'}];h.render();h.click('tool_open',{id:'existing-request'});await flush();
 const footer=h.footer,save=h.buttons.find(button=>button.dataset.authorAction==='tool_save'),review=h.buttons.find(button=>button.dataset.authorAction==='tool_review'),name=h.fields.find(field=>field.name==='name');assert.equal(review.disabled,false);
 for(const [field,value,event,reason] of [['name','최신 도구 이름','input',/초안을 먼저/],['name','최신 도구 이름','change',/초안을 먼저/],['guide_url','','input',/가이드 문서 링크/],['guide_url','https://example.invalid/new-guide','change',/초안을 먼저/],['output_schema_json','{','input',/결과 형식을 확인/],['output_schema_json',JSON.stringify(schema),'change',/초안을 먼저/],['description','최신 설명','input',/초안을 먼저/],['description','최신 설명','change',/초안을 먼저/]]){h.field(field,value,event);assert.equal(h.footer,footer);assert.equal(h.buttons.find(button=>button.dataset.authorAction==='tool_save'),save);assert.equal(h.buttons.find(button=>button.dataset.authorAction==='tool_review'),review);assert.equal(h.fields.find(field=>field.name==='name'),name);assert.equal(review.disabled,true);assert.equal(h.footerNodes['[data-tool-summary]'].textContent,'저장 안 됨');assert.match(h.footerNodes['#ew-tool-submit-reason'].textContent,reason);}
 assert.equal(h.footerReplacements || 0,0);h.click('tool_save');await flush();assert.equal(h.operations.length,1);assert.equal(h.operations[0].tool.name,'최신 도구 이름');assert.equal(h.operations[0].tool.description,'최신 설명');assert.equal(h.operations[0].tool.guide_url,'https://example.invalid/new-guide');assert.deepEqual(h.operations[0].tool.output_schema,schema);assert.equal(h.buttons.find(button=>button.dataset.authorAction==='tool_review').disabled,false);
});

test('tool starter questions use the same source help callback without mutating the draft and disable during a response',async()=>{
 const h=harness();h.selection.tab='tools';h.render();h.click('tool_create');await flush();const before=h.draft(),sent=[];let busy=true;
 h.callbacks.helpState=()=>({busy});h.callbacks.askHelp=async(question,context)=>{sent.push({question,context});return true;};
 h.designer.syncHelpState();assert.equal(h.buttons.filter(button=>button.dataset.authorAction==='tool_question').every(button=>button.disabled),true);
 busy=false;h.designer.syncHelpState();assert.equal(h.buttons.filter(button=>button.dataset.authorAction==='tool_question').every(button=>!button.disabled),true);
 h.click('tool_question',{id:'0'});await flush();assert.equal(sent.length,1);assert.equal(sent[0].question,'정보 읽기 도구와 작업 부탁 도구는 뭐가 달라?');assert.equal(sent[0].context.screen,'새 도구 시작');assert.deepEqual(h.draft(),before);assert.equal(h.writes.length,0);assert.equal(h.operations.length,0);assert.doesNotMatch(h.markup,/질문을 입력창에 채웁니다/);
});

test('unreceived procedure scope retains heading and controls without claiming an empty list or zero count',()=>{
 const h=harness();h.selection={...h.selection,system_id:'APC',workflow_id:''};h.state={...h.state,workflow:null,workflows:[]};
 h.designer.render({state:h.state,selection:h.selection,host:h.host,scope_loading:true});
 assert.match(h.markup,/전체 공장 · APC에서 사용할 업무를 작성합니다/);assert.match(h.markup,/data-ees-scope-loading="panel"[^>]*>받는 중/);assert.match(h.markup,/id="ew-author-search"/);assert.match(h.markup,/data-author-action="create"/);assert.doesNotMatch(h.markup,/<small>0개<|아직 워크플로우가 없습니다/);
 h.designer.render({state:h.state,selection:h.selection,host:h.host,scope_loading:false});assert.match(h.markup,/<small>0개<\/small>/);assert.match(h.markup,/아직 워크플로우가 없습니다/);
});

function sharedReviewFixture(h){
 const search={id:'managed-search_pages',function:'search_pages',name:'Confluence 페이지 찾기',target:'Confluence',state:'available',can_use:true,version:1,revision:1,input_schema:{properties:{query:{type:'string'},space_key:{type:'string',default:''},limit:{type:'integer',default:10}},required:['query']},output_schema:{kind:'list',fields:['id','title','url']}};
 const read={...copy(search),id:'managed-get_page',function:'get_page',name:'Confluence 페이지 읽기',input_schema:{properties:{page_id:{type:'string'}},required:['page_id']},output_schema:{kind:'evidence',fields:['data','evidence']}};
 h.state.operations={shared_tools:[search,read],tools:[]};return {search,read};
}
test('shared tool switching removes only generated inputs bindings and result shape',async()=>{
 const h=harness();sharedReviewFixture(h);h.workflows.get('w').draft.nodes.j.inputs=[{id:'memo',name:'직접 입력',type:'text',scope:'run',required:false}];h.render();await h.node();
 h.click('pick_job_tool',{id:'managed-search_pages',shared:'true'});await flush();
 assert.equal(h.draft().definition.nodes.j.inputs.find(x=>x.id==='query').source.shared_tool_id,'managed-search_pages');
 h.click('pick_job_tool',{id:'managed-get_page',shared:'true'});await flush();
 let j=h.draft().definition.nodes.j;assert.deepEqual(j.inputs.map(x=>x.id),['memo','page_id']);assert.deepEqual(Object.keys(j.argument_bindings),['page_id']);
 h.click('pick_job_tool',{id:''});await flush();j=h.draft().definition.nodes.j;
 assert.deepEqual(j.inputs.map(x=>x.id),['memo']);assert.deepEqual(j.argument_bindings||{},{});assert.equal(j.result_block,'human_confirm');assert.equal(j.shared_tool_id,undefined);
 h.click('pick_job_tool',{id:'managed-search_pages',shared:'true'});await flush();
 h.state.operations.tools=[{id:'legacy',name:'이전 계약',state:'approved',revision:2,reference:{tool_id:'native',function:'read'}}];h.render();
 h.click('pick_job_tool',{id:'legacy'});await flush();j=h.draft().definition.nodes.j;
 assert.deepEqual(j.inputs.map(x=>x.id),['memo']);assert.deepEqual(j.argument_bindings||{},{});assert.equal(j.tool_contract_id,'legacy');assert.equal(j.result_block,'human_confirm');
});
test('shared detail only offers review when needed and shows Korean input types',async()=>{
 const h=harness();const {search}=sharedReviewFixture(h);h.state.capabilities.is_admin=true;h.selection.tab='tools';h.render();h.click('shared_open',{id:search.id});await flush();
 assert.doesNotMatch(h.markup,/data-author-action="shared_review"/);assert.match(h.markup,/찾을 말/);assert.match(h.markup,/글자/);assert.match(h.markup,/숫자/);assert.doesNotMatch(h.markup,/query · string/);
 search.state='disabled';h.render();assert.doesNotMatch(h.markup,/data-author-action="shared_review"/);
 search.state='review_required';h.render();assert.match(h.markup,/data-author-action="shared_review"/);
});
test('legacy to shared explicit selection drops foreign bindings and keeps manually declared inputs',async()=>{const h=harness();sharedReviewFixture(h);const job=h.workflows.get('w').draft.nodes.j;Object.assign(job,{mode:'tool',tool_contract_id:'legacy',tool_contract_revision:1,tool_reference:{tool_id:'native',function:'read'},inputs:[{id:'memo',name:'직접 만든 값',type:'text',scope:'run'}],argument_bindings:{issue_keys:{result:{job_id:'confirmed-list',path:['items'],value_field:'id',confirmed:true}},memo:{input:'memo'}}});h.render();await h.node();await a12Connect(h,'managed-search_pages');const selected=h.draft().definition.nodes.j;assert.deepEqual(Object.keys(selected.argument_bindings).sort(),['limit','query','space_key']);assert.equal(selected.inputs[0].id,'memo');assert.equal(selected.tool_contract_id,undefined);assert.equal(selected.tool_reference,undefined);});

test('tool setup does not introduce unsupported result handoffs and preserves existing legacy links',async()=>{const h=harness();await c66SelectShared(h);await a12Open(h);assert.doesNotMatch(h.modalMarkup,/value="result"|name="result_argument"|name="result_job_id"/);await h.modalClose('cancel');const value=h.draft().definition;value.nodes.j.argument_bindings.query={result:{job_id:'old',path:['items'],extension:'keep'}};h.designer.reset();installDefinition(h,value);await h.node();await a12Open(h);assert.match(h.modalMarkup,/기존 연결 유지/);await h.modalClose('apply');assert.deepEqual(h.draft().definition,value);});

test('shared review names changed categories without exposing references and separates access controls',async()=>{
 for(const [field,label] of [['content_hash','도구 코드'],['schema_hash','입력 형식'],['config_hash','연결 설정'],['environment','실행 환경']]){
  const h=harness(),{search}=sharedReviewFixture(h);h.state.capabilities.is_admin=true;h.selection.tab='tools';search.state='review_required';
  search.reference={tool_id:'private-native-id',function:'search_pages',content_hash:'private-code',schema_hash:'private-schema',config_hash:'private-config',environment:'private-runtime'};
  search.observed_reference={...search.reference,[field]:'changed-private-value'};search.observed_input_schema=copy(search.input_schema);search.observed_output_schema=copy(search.output_schema);
  h.render();h.click('shared_open',{id:search.id});await flush();h.dialogs.push(null);h.click('shared_review',{id:search.id});await flush();
  const dialog=JSON.stringify(h.dialogHistory.at(-1));assert.match(dialog,new RegExp('바뀐 항목: '+label));assert.doesNotMatch(dialog,/private-|changed-private/);assert.match(dialog,/ew-shared-access/);assert.match(dialog,/<fieldset><legend>쓸 수 있는 그룹<\/legend>[\s\S]*<\/fieldset><label>담당/);
 }
});

test('shared tool reselection preserves customized compatible bindings and manual inputs',async()=>{
 const h=harness();sharedReviewFixture(h);h.render();await h.node();
 h.click('pick_job_tool',{id:'managed-search_pages',shared:'true'});await flush();
 h.dialogs.push({id:'custom_query',name:'직접 지정한 검색어',type:'text',scope:'run',required:true,tool_argument:'query'});h.click('input_add');await flush();
 for(const viaNone of [false,true]){
  if(viaNone){h.click('pick_job_tool',{id:''});await flush();}
  h.click('pick_job_tool',{id:'managed-search_pages',shared:'true'});await flush();
  const job=h.draft().definition.nodes.j;assert.deepEqual(job.argument_bindings.query,{input:'custom_query'});
  assert.ok(job.inputs.some(field=>field.id==='custom_query'));assert.ok(!job.inputs.some(field=>field.id==='query'));
 }
});

test('unavailable reviewed shared tool offers persistent disable using its saved reference',async()=>{
 const h=harness(),{search}=sharedReviewFixture(h);h.state.capabilities.is_admin=true;h.selection.tab='tools';search.state='unavailable';search.reference={tool_id:'saved',function:'search_pages'};search.observed_reference=null;
 h.render();h.click('shared_open',{id:search.id});await flush();assert.match(h.markup,/data-author-action="shared_disable"/);assert.doesNotMatch(h.markup,/data-author-action="shared_review"|data-author-action="shared_enable"/);
 h.dialogs.push({});h.click('shared_disable');await flush();assert.deepEqual(h.operations[0].reference,search.reference);
 search.group_ids=['existing'];h.state.native_groups=[{id:'existing',name:'기존 그룹'},{id:'other',name:'새 그룹'}];h.state.native_users=[{id:'admin',name:'관리자'}];
 h.dialogs.push({owner:'admin','group:existing':false});h.click('shared_access');await flush();
 assert.deepEqual(h.operations[1].group_ids,[]);assert.deepEqual(h.operations[1].reference,search.reference);
 assert.match(h.dialogHistory.at(-1).html,/모두 해제/);assert.doesNotMatch(h.dialogHistory.at(-1).html,/group:other/);
});

test('shared tool use opens its recorded system with the workflow',async()=>{
 const h=harness(),{search}=sharedReviewFixture(h);search.uses=[{workflow_id:'fdc-workflow',workflow_name:'FDC 절차',job_name:'조회',system_id:'FDC'}];
 h.selection.tab='tools';h.render();h.click('shared_open',{id:search.id});await flush();
 assert.match(h.markup,/data-id="fdc-workflow" data-system-id="FDC"/);
 const opened=[];h.callbacks.openWorkflow=async(...args)=>opened.push(args);
 h.click('open',{id:'fdc-workflow',systemId:'FDC'});await flush();assert.deepEqual(opened,[['fdc-workflow','FDC']]);
});

test('shared discovery failure is explicit while legacy tools remain usable',async()=>{
 const h=harness();sharedReviewFixture(h);h.state.operations.shared_tools=[];h.state.operations.shared_tools_notice='공용 도구 목록을 불러오지 못했습니다.';h.state.operations.tools=[{id:'kept-legacy',name:'기존 계약 보존',kind:'read',state:'approved',revision:1,reference:{tool_id:'old',function:'search_pages'}}];
 h.selection.tab='tools';h.render();assert.match(h.markup,/공용 도구 목록을 불러오지 못했습니다/);assert.doesNotMatch(h.markup,/공용 도구 0개/);assert.match(h.markup,/기존 계약 보존/);
 h.selection.tab='overview';h.render();await h.node();h.field('mode','tool','change');await flush();assert.match(h.markup,/공용 도구 목록을 불러오지 못했습니다/);
});


test('B10 common heading empty list and unreviewed labels follow the specification cards',async()=>{
 const h=harness();const {search}=sharedReviewFixture(h);h.state.capabilities.is_admin=true;h.selection.tab='tools';search.version=0;search.state='review_required';h.render();
 const header=h.markup.match(/<header>([\s\S]*?)<\/header>/)?.[1];assert.ok(header);assert.match(header,/<strong>도구 · 공용<\/strong>/);assert.doesNotMatch(header,/<small\b/);assert.match(header,/data-action="close_panel"/);assert.match(h.markup,/data-author-tab="tools"/);assert.match(h.markup,/data-state="unreviewed">확인 전<\/span>/);assert.doesNotMatch(h.markup,/data-state="review_required">도구 확인 필요/);
 h.click('shared_open',{id:search.id});await flush();assert.match(h.markup,/지금 버전 확인 전/);assert.match(h.markup,/data-state="unreviewed">확인 전<\/span>/);
 h.click('shared_list');await flush();h.state.operations.shared_tools=[];h.render();assert.match(h.markup,/공용 도구 0개/);assert.match(h.markup,/쓸 수 있는 공용 도구가 없습니다. 필요한 도구는 관리자에게 요청하세요./);
});
test('A12 workflow picker removes read badges and preserves the empty-catalog next action',async()=>{const h=harness();sharedReviewFixture(h);h.render();await h.node();h.field('mode','tool','change');await flush();await a12Open(h);assert.doesNotMatch(h.modalMarkup,/>조회<|class="ew-author-tag"/);assert.match(h.modalMarkup,/data-job-tool-candidate="shared:managed-search_pages"/);await h.modalClose('cancel');h.state.operations.shared_tools=[];h.render();await a12Open(h);assert.match(h.modalMarkup,/쓸 수 있는 도구가 없습니다. 관리자에게 요청해 주세요./);await h.modalClose('cancel');});

test('B10 neutral unreviewed badge does not alter server review state or conceal a reviewed tool warning',async()=>{
 const h=harness(),{search}=sharedReviewFixture(h);h.state.capabilities.is_admin=true;h.selection.tab='tools';search.version=0;search.state='review_required';h.render();
 assert.match(h.markup,/data-state="unreviewed">확인 전<\/span>/);assert.equal(search.state,'review_required');
 h.click('shared_open',{id:search.id});await flush();assert.match(h.markup,/data-state="unreviewed">확인 전<\/span>/);assert.match(h.markup,/data-author-action="shared_review"/);
 search.version=1;h.render();assert.match(h.markup,/data-state="review_required">도구 확인 필요<\/span>/);assert.doesNotMatch(h.markup,/data-state="unreviewed"/);assert.match(h.markup,/data-author-action="shared_review"/);
 search.state='preparing';search.version=0;h.render();assert.match(h.markup,/data-state="preparing">준비 중<\/span>/);assert.doesNotMatch(h.markup,/data-state="unreviewed"/);
});

test('C44 inline edits are isolated until apply, survive tabs, and cancel only their own values',async()=>{
 const h=harness();await h.node();h.field('job_guidance','미저장 작업 안내');
 h.click('edit_workflow');await flush();h.field('name','아직 적용 안 함');h.field('category','setup');
 assert.equal(h.draft().definition.name,'절차 w');
 h.click('tab',{tab:'history'});await flush();h.click('tab',{tab:'content'});await flush();
 assert.equal(h.fields.find(field=>field.name==='name').value,'아직 적용 안 함');
 h.click('save');await flush();assert.equal(h.writes.length,0);assert.match(h.markup,/적용하거나 취소/);
 h.click('summary_cancel');await flush();assert.equal(h.draft().definition.name,'절차 w');assert.equal(h.draft().definition.nodes.j.instructions,'미저장 작업 안내');
 h.click('summary_edit',{id:'business'});await flush();h.field('category','setup');h.field('description','개인 PC 준비');
 h.click('summary_apply');await flush();assert.equal(h.draft().definition.category,'setup');assert.equal(h.draft().dirty,true);assert.equal(h.writes.length,0);
 h.click('save');await flush();assert.equal(h.writes.at(-1).definition.nodes.j.instructions,'미저장 작업 안내');assert.equal(h.writes.at(-1).definition.description,'개인 PC 준비');
});
test('C44 optional settings require explicit review and never replace server validation',async()=>{
 // C66 retires summary review controls, not stored authoring_review decisions or server validation.
 const h=harness(),review={inputs:true,rules:true,unknown_review:{keep:true}};h.workflows.get('w').validation=null;h.workflows.get('w').draft.authoring_review=copy(review);h.render();
 assert.doesNotMatch(h.markup,/6개 중|data-author-action="summary_optional"|정해야 할 것/);
 assert.equal(h.buttons.some(button=>button.dataset.authorAction==='publish'&&!button.disabled),false);assert.equal(h.writes.length,0);
 await h.node();h.field('result_block','item_verdict');await flush();assert.deepEqual(h.draft().definition.authoring_review,review);
 h.click('save');await flush();assert.deepEqual(h.writes.at(-1).definition.authoring_review,review);assert.equal(h.workflows.get('w').validation,null);
 h.click('publish');await flush();assert.equal(h.writes.length,1,'stored optional review never substitutes for server validation');
 await h.open('q');await h.open('w');h.click('tab',{tab:'content'});await flush();assert.deepEqual(h.draft().definition.authoring_review,review);
});
test('C44 when editor preserves schedule extensions and cancelled mode changes',async()=>{
 const h=harness();h.workflows.get('w').draft.schedule={stage_deadlines:{t:{offset_days:-2}},opening:'on_schedule'};h.render();
 // C66 removes the summary-only "when" editor. Use the existing schedule tab and retain extension/cancel isolation checks.
 h.click('tab',{tab:'schedule'});await flush();h.click('run_mode',{id:'periodic'});await flush();
 h.field('frequency','weekly');h.field('anchor','2026-10-19T09:00');h.field('interval','2');await flush();
 const draft=h.draft().definition;assert.equal(draft.mode,'periodic');assert.deepEqual(draft.schedule.stage_deadlines,{t:{offset_days:-2}});assert.equal(draft.schedule.interval,2);assert.equal(h.writes.length,0);
 h.click('tab',{tab:'content'});h.click('summary_edit',{id:'business'});await flush();h.field('execution_scope','factory','change');h.click('summary_cancel');await flush();assert.deepEqual(h.draft().definition,draft);assert.deepEqual(h.workflows.get('w').draft.schedule,{stage_deadlines:{t:{offset_days:-2}},opening:'on_schedule'});
});
test('C44 save and validation failures retain input and allow explicit retry',async()=>{
 const h=harness();h.click('edit_workflow');await flush();h.field('description','재시도할 내용');h.click('summary_apply');await flush();
 h.writeOverride=async()=>{throw new Error('합성 저장 실패');};h.click('save');await flush();assert.equal(h.draft().definition.description,'재시도할 내용');assert.equal(h.draft().dirty,true);
 h.writeOverride=null;h.click('save');await flush();assert.equal(h.draft().dirty,false);
 h.writeOverride=async()=>{throw new Error('합성 검사 실패');};h.click('validate');await flush();assert.equal(h.draft().definition.description,'재시도할 내용');
 h.writeOverride=null;h.click('validate');await flush();assert.equal(h.writes.at(-1).action,'validate_workflow');
});
test('C44 inline buffers are scoped to workflow and cleared on account change',async()=>{
 const h=harness();h.click('edit_workflow');await flush();h.field('description','계정 a 비공개');
 await h.open('q');assert.doesNotMatch(h.markup,/계정 a 비공개/);await h.open('w');h.click('tab',{tab:'content'});await flush();assert.match(h.markup,/계정 a 비공개/);
 h.state.capabilities.actor_id='b';h.render();assert.doesNotMatch(h.markup,/계정 a 비공개/);
});
test('C44 no permission cannot apply an already open inline edit',async()=>{
 const h=harness();h.click('edit_workflow');await flush();h.field('name','권한 회수 뒤 변경');
 h.state.capabilities.can_author=false;h.state.capabilities.managed_systems=[];h.state.workflow.can_manage=false;h.render();
 h.click('summary_apply');await flush();assert.equal(h.draft().definition.name,'절차 w');assert.equal(h.writes.length,0);
});

test('deleting a stage removes only its draft schedule deadline and preserves dangling job dependencies',async()=>{
 const h=harness();h.workflows.get('w').draft.schedule={stage_deadlines:{t:{offset_days:-2},other:{offset_days:4}},extension:'preserve'};h.render();await h.node('t');
 h.dialogs.push({});h.click('delete_node',{id:'t'});await flush();
 const draft=h.draft();assert.equal(draft.definition.nodes.t,undefined);assert.equal(draft.definition.nodes.j,undefined);
 assert.equal(Object.hasOwn(draft.definition.schedule.stage_deadlines,'t'),false);assert.deepEqual(draft.definition.schedule.stage_deadlines.other,{offset_days:4});assert.equal(draft.definition.schedule.extension,'preserve');assert.equal(draft.dirty,true);assert.equal(h.writes.length,0);
});

test('inline creation cancellation restores its trigger and preserves private name and purpose buffers',async()=>{
 for(const escape of [false,true]){
  const h=harness();await beginCreation(h,'다시 쓸 이름','다시 쓸 목적');if(escape)h.escape('#ew-procedure-create');else h.click('procedure_cancel');await flush();
  assert.equal(h.document.activeElement,actionButton(h,'create'));assert.equal(h.writes.length,0);h.click('create');await flush();assert.equal(h.fields.find(field=>field.id==='ew-procedure-name').value,'다시 쓸 이름');assert.equal(h.fields.find(field=>field.id==='ew-procedure-description').value,'다시 쓸 목적');assert.equal(h.document.activeElement,h.fields.find(field=>field.id==='ew-procedure-name'));
 }
});

test('content renders 0 1 3 and 6 stages initially collapsed with exactly one expanded',async()=>{
 for(const count of [0,1,3,6]){const h=harness();installDefinition(h,stagedDefinition(count));
  assert.equal(h.buttons.filter(button=>button.dataset.authorAction==='stage_toggle').length,count);
  assert.equal(h.buttons.filter(button=>button.getAttribute('aria-expanded')==='true').length,0);
  assert.equal(h.buttons.filter(button=>button.dataset.authorAction==='node'&&button.dataset.id).length,0);
  assert.match(h.markup,new RegExp('단계 '+count+'개'));
  if(!count){assert.match(h.markup,/아직 단계가 없습니다. 먼저 단계를 추가하세요./);continue;}
  h.click('stage_toggle',{id:'t0'});await flush();assert.equal(stageButton(h,'t0').getAttribute('aria-expanded'),'true');
  if(count>1){h.click('stage_toggle',{id:'t1'});await flush();assert.equal(stageButton(h,'t0').getAttribute('aria-expanded'),'false');assert.equal(stageButton(h,'t1').getAttribute('aria-expanded'),'true');}
  const last=count>1?'t1':'t0';assert.equal(h.buttons.filter(button=>button.dataset.authorAction==='stage_toggle'&&button.getAttribute('aria-expanded')==='true').length,1);
  assert.equal(h.document.activeElement,stageButton(h,last));h.click('stage_toggle',{id:last});await flush();assert.equal(stageButton(h,last).getAttribute('aria-expanded'),'false');assert.equal(h.document.activeElement,stageButton(h,last));assert.equal(h.draft().dirty,false);assert.equal(h.writes.length,0);
 }
});
test('stage inline edit changes only name and multiline description and has no job execution fields',async()=>{
 const h=harness(),value=stagedDefinition(1);Object.assign(value.nodes.t0,{instructions:'보존할 수행 안내',human_values:{memo:'보존'},inputs:[{id:'x',type:'text',name:'기존 입력'}],tool_reference:{tool_id:'opaque',function:'keep'},completion:{rule:'keep'},extra:{nested:['keep']}});installDefinition(h,value);
 h.click('stage_toggle',{id:'t0'});h.click('stage_edit',{id:'t0'});await flush();
 assert.match(h.markup,/id="ew-stage-editor"/);assert.match(h.markup,/단계 이름/);assert.match(h.markup,/이 단계에서 하는 일/);assert.match(h.markup,/name="name"[^>]*maxlength="160"/);
 for(const field of ['mode','result_block','tool_contract_id','completion_rule','depends_on','input_id'])assert.equal(h.forms['ew-stage-editor'].controls.some(control=>control.name===field),false,field);
 assert.match(h.markup,/<details[^>]*>[\s\S]*?<summary>추가 설정/);h.field('name','새 단계 이름');h.field('description','바뀐 첫 줄\n바뀐 둘째 줄');assert.deepEqual(h.draft().definition.nodes.t0,value.nodes.t0);
 h.click('inline_apply');await flush();const updated=h.draft().definition.nodes.t0;assert.equal(updated.description,'바뀐 첫 줄\n바뀐 둘째 줄');assert.deepEqual(updated,{...value.nodes.t0,name:'새 단계 이름',description:'바뀐 첫 줄\n바뀐 둘째 줄'});assert.equal(h.draft().dirty,true);assert.equal(h.writes.length,0);
});
// C61 replaces stale-on-Apply name errors with immediate form-level notices.
// Buffer/latest-definition/no-write checks below remain; submit still exercises the last guard.
test('stage inline revision conflict preserves the buffer and latest draft across workflow reentry',async()=>{
 const h=harness();installDefinition(h,stagedDefinition(1,1));await beginInline(h,'stage');h.field('name','내가 작성한 단계');h.field('description','내가 작성한 설명');
 const record=h.workflows.get('w');record.revision=2;Object.assign(record.draft.nodes.t0,{name:'다른 작성자의 단계',description:'다른 작성자의 설명'});h.render();
 assert.equal(h.draft().revision,2);assert.equal(h.fields.find(field=>field.name==='name').value,'내가 작성한 단계');const latest=h.draft();assertUnavailableInline(h,staleInlineMessage);
 await submitInline(h);assert.deepEqual(h.draft(),latest);assert.equal(h.forms['ew-stage-editor'].controls.find(field=>field.name==='description').value,'내가 작성한 설명');assertUnavailableInline(h,staleInlineMessage);assert.equal(h.document.activeElement,h.forms['ew-stage-editor'].controls.find(field=>field.name==='description'));assert.equal(h.writes.length,0);
 await h.open('q');await h.open('w');await submitInline(h);assert.deepEqual(h.draft(),latest);assert.equal(h.fields.find(field=>field.name==='name').value,'내가 작성한 단계');assertUnavailableInline(h,staleInlineMessage);
 h.click('inline_cancel');await flush();assert.equal(h.document.activeElement.dataset.authorAction,'stage_edit');assert.equal(h.document.activeElement.dataset.id,'t0');h.click('stage_edit',{id:'t0'});await flush();assert.equal(h.fields.find(field=>field.name==='name').value,'다른 작성자의 단계');assert.equal(h.fields.find(field=>field.name==='description').value,'다른 작성자의 설명');await h.inline('최신 초안에서 수정');assert.equal(h.draft().definition.nodes.t0.name,'최신 초안에서 수정');assert.equal(h.draft().definition.nodes.t0.description,'다른 작성자의 설명');assert.equal(h.draft().revision,2);assert.equal(h.draft().dirty,true);assert.equal(h.writes.length,0);
});
for(const kind of ['add_stage','add_job'])test(kind+' inline form cannot attach an old buffer to a newer saved draft',async()=>{
 const h=harness();installDefinition(h,stagedDefinition(1,1));await beginInline(h,kind);h.field('name','아직 추가하지 않은 이름');
 const record=h.workflows.get('w');record.revision=2;record.draft.nodes.t0.name='최신 단계';h.render();const latest=h.draft();assert.equal(latest.revision,2);assertUnavailableInline(h,staleInlineMessage);
 await submitInline(h);assert.deepEqual(h.draft(),latest);assert.equal(h.fields.find(field=>field.name==='name').value,'아직 추가하지 않은 이름');assertUnavailableInline(h,staleInlineMessage);assert.equal(h.writes.length,0);
 h.click('inline_cancel');await flush();assert.equal(h.document.activeElement.dataset.authorAction,kind);if(kind==='add_job')assert.equal(h.document.activeElement.dataset.parent,'t0');assert.deepEqual(h.draft(),latest);
});
for(const kind of ['stage','add_job'])test('remote stage deletion keeps the '+kind+' inline buffer reviewable and cancellable',async()=>{
 const h=harness();installDefinition(h,stagedDefinition(2,1));await beginInline(h,kind);h.field('name','삭제 전 작성한 이름');if(kind==='stage')h.field('description','삭제 전 작성한 설명');
 const record=h.workflows.get('w');record.revision=2;h.helpers.removeNode(record.draft,'t0');h.render();const latest=h.draft();assert.equal(latest.revision,2);assert.equal(latest.definition.nodes.t0,undefined);assertUnavailableInline(h,deletedInlineMessage);
 h.click('add_stage');await flush();assert.deepEqual(h.draft(),latest);assert.ok(h.forms['ew-stage-editor'],'remote deletion must leave a visible way to review and cancel the blocked buffer');assert.equal(h.forms['ew-stage-editor'].controls.find(field=>field.name==='name').value,'삭제 전 작성한 이름');if(kind==='stage')assert.equal(h.fields.find(field=>field.name==='description').value,'삭제 전 작성한 설명');assertUnavailableInline(h,deletedInlineMessage);assert.doesNotMatch(inlineMarkup(h),/추가 설정|저장된 초안이 바뀌었습니다/);assert.equal(h.scrollRequests.at(-1).node,h.forms['ew-stage-editor'].inlineError);
 await submitInline(h);assert.deepEqual(h.draft(),latest);assertUnavailableInline(h,deletedInlineMessage);assert.equal(h.writes.length,0);
 h.click('inline_cancel');await flush();assert.equal(h.forms['ew-stage-editor'],undefined);assert.deepEqual(h.draft(),latest);assert.equal(h.document.activeElement.dataset.authorAction,'add_stage');h.click('stage_toggle',{id:'t1'});await flush();assert.equal(stageButton(h,'t1').getAttribute('aria-expanded'),'true');assert.equal(h.writes.length,0);
});
test('C61 remote deletion moves a disappearing advanced-settings button focus to Cancel',async()=>{
 const h=harness();installDefinition(h,stagedDefinition(2,1));await beginInline(h,'stage');h.field('name','보존할 단계 이름');const advanced=actionButton(h,'node','t0');assert.equal(advanced.tagName,'BUTTON');assert.equal(advanced.closest('#ew-stage-editor'),h.forms['ew-stage-editor']);advanced.focus();
 const record=h.workflows.get('w');record.revision=2;h.render();assert.equal(h.document.activeElement,actionButton(h,'node','t0'),'revision-only refresh keeps the existing focused button');
 record.revision=3;h.helpers.removeNode(record.draft,'t0');h.render();const latest=h.draft();assert.equal(actionButton(h,'node','t0'),undefined);assert.equal(h.document.activeElement?.dataset.authorAction,'inline_cancel');assertUnavailableInline(h,deletedInlineMessage);assert.equal(h.fields.find(field=>field.name==='name').value,'보존할 단계 이름');await submitInline(h);assert.deepEqual(h.draft(),latest);assert.equal(h.writes.length,0);
});
test('C61 remote deletion moves a disappearing stage header button focus to Cancel',async()=>{
 const h=harness();installDefinition(h,stagedDefinition(2,1));await beginInline(h,'stage');h.field('name','내 입력 보존');stageButton(h,'t0').focus();const record=h.workflows.get('w');record.revision=2;h.helpers.removeNode(record.draft,'t0');h.render();
 assert.equal(stageButton(h,'t0'),undefined);assert.equal(h.document.activeElement?.dataset.authorAction,'inline_cancel');assertUnavailableInline(h,deletedInlineMessage);assert.equal(h.fields.find(field=>field.name==='name').value,'내 입력 보존');assert.equal(h.draft().definition.nodes.t0,undefined);assert.equal(h.writes.length,0);
});
for(const kind of ['stage','add_job'])test('C61 missing '+kind+' parent is unavailable even at the same revision',async()=>{
 const h=harness();installDefinition(h,stagedDefinition(2,1));await beginInline(h,kind);h.field('name','지워지기 전에 쓴 이름');h.helpers.removeNode(h.workflows.get('w').draft,'t0');h.render();const latest=h.draft();
 assert.equal(latest.revision,1);assertUnavailableInline(h,deletedInlineMessage);await submitInline(h);assert.deepEqual(h.draft(),latest);assert.equal(latest.definition.nodes.t0,undefined);assert.equal(h.fields.find(field=>field.name==='name').value,'지워지기 전에 쓴 이름');assert.equal(h.writes.length,0);assert.equal(h.operations.length,0);
});
for(const kind of ['stage','add_stage','add_job']){
 test('C61 '+kind+' stale refresh preserves input focus and selection before any click',async()=>{
  const h=harness();installDefinition(h,stagedDefinition(2,1));await beginInline(h,kind);h.field('name','보존할 입력');h.fields.find(field=>field.name==='name').setSelectionRange(1,4);h.workflows.get('w').revision=2;h.render();
  assertUnavailableInline(h,staleInlineMessage);const field=h.forms['ew-stage-editor'].controls.find(field=>field.name==='name');assert.equal(h.document.activeElement,field);assert.equal(field.selectionStart,1);assert.equal(field.selectionEnd,4);assert.equal(field.value,'보존할 입력');assert.equal(h.writes.length,0);
 });
 test('C61 '+kind+' stale refresh supersedes an earlier field error without stealing outside focus',async()=>{
  const h=harness();installDefinition(h,stagedDefinition(2,1));await beginInline(h,kind);h.field('name','');await submitInline(h);assert.match(inlineMarkup(h),/id="ew-stage-name-error"/);const outside={id:'native-chat-input'};h.document.activeElement=outside;h.workflows.get('w').revision=2;h.render();
  assertUnavailableInline(h,staleInlineMessage);assert.equal(h.document.activeElement,outside);const latest=h.draft();await submitInline(h);assert.deepEqual(h.draft(),latest);assertUnavailableInline(h,staleInlineMessage);assert.equal(h.document.activeElement,outside);assert.equal(h.writes.length,0);
 });
 test('C61 '+kind+' disappearing apply focus moves only to Cancel',async()=>{
  const h=harness();installDefinition(h,stagedDefinition(2,1));await beginInline(h,kind);h.field('name','보존할 입력');h.buttons.find(button=>button.dataset.authorAction==='inline_apply').focus();h.workflows.get('w').revision=2;h.render();
  assert.equal(h.document.activeElement?.dataset.authorAction,'inline_cancel');assertUnavailableInline(h,staleInlineMessage);assert.equal(h.writes.length,0);
 });
 test('C61 '+kind+' stale submit with an empty name creates no field error or writes',async()=>{
  const h=harness();installDefinition(h,stagedDefinition(2,1));await beginInline(h,kind);h.field('name','');h.workflows.get('w').revision=2;h.render();const latest=h.draft();
  await submitInline(h);assert.deepEqual(h.draft(),latest);assert.equal(h.writes.length,0);assert.equal(h.operations.length,0);assertUnavailableInline(h,staleInlineMessage);assert.equal(h.fields.find(field=>field.name==='name').value,'');
 });
 test('C61 '+kind+' dirty stale buffer blocks other stage job and add actions with its own notice',async()=>{
  const h=harness();installDefinition(h,stagedDefinition(2,1));await beginInline(h,kind);h.field('name','보존할 입력');h.workflows.get('w').revision=2;h.render();const latest=h.draft();
  for(const [action,data] of [['stage_toggle',{id:'t1'}],['node',{id:'j0-0'}],['add_stage',{}],['add_job',{parent:'t1'}],['stage_menu',{id:'t0'}]]){h.click(action,data);await flush();assertUnavailableInline(h,staleInlineMessage);assert.equal(h.fields.find(field=>field.name==='name').value,'보존할 입력');assert.deepEqual(h.draft(),latest);assert.equal(h.scrollRequests.at(-1).node,h.forms['ew-stage-editor'].inlineError);assert.deepEqual(copy(h.scrollRequests.at(-1).options),{block:'nearest',inline:'nearest',behavior:'instant'});}
  assert.equal(h.writes.length,0);assert.equal(h.operations.length,0);const result=h.escape('#ew-stage-editor');await flush();assert.deepEqual(copy(result),{handled:true,preventDefault:true});assert.equal(h.forms['ew-stage-editor'],undefined);assert.deepEqual(h.draft(),latest);
 });
 test('C61 '+kind+' same revision keeps Apply and submit while name validation remains field-specific',async()=>{
  const h=harness();installDefinition(h,stagedDefinition(2,1));await beginInline(h,kind);const before=h.draft();h.render();assert.ok(h.buttons.find(button=>button.dataset.authorAction==='inline_apply'));assert.doesNotMatch(inlineMarkup(h),/저장된 초안이 바뀌었습니다/);
  for(const value of ['', '긴'.repeat(161)]){h.field('name',value);await submitInline(h);const html=inlineMarkup(h);assert.match(html,/<input\b[^>]*name="name"[^>]*aria-invalid="true"[^>]*aria-describedby="ew-stage-name-error"/);assert.match(html,/id="ew-stage-name-error"/);assert.match(html,value?/이름은 160자 이내로 입력해 주세요./:kind==='add_job'?/작업 이름을 입력해 주세요./:/단계 이름을 입력해 주세요./);assert.deepEqual(h.draft(),before);}
  h.field('name','같은 버전의 정상 이름');await submitInline(h);assert.equal(h.forms['ew-stage-editor'],undefined);assert.equal(Object.values(h.draft().definition.nodes).filter(node=>node.name==='같은 버전의 정상 이름').length,1);assert.equal(h.draft().revision,1);assert.equal(h.draft().dirty,true);assert.equal(h.writes.length,0);assert.equal(h.operations.length,0);
 });
}
test('same revision polls allow inline apply and same revision proposal replacement closes only a clean form',async()=>{
 const h=harness();installDefinition(h,stagedDefinition(1,1));h.click('stage_edit',{id:'t0'});await flush();h.field('name','같은 버전에서 수정');h.render();await h.inline('같은 버전에서 수정');assert.equal(h.draft().definition.nodes.t0.name,'같은 버전에서 수정');assert.equal(h.draft().revision,1);
 h.click('stage_edit',{id:'t0'});await flush();const next=h.draft().definition;next.nodes.t0.name='대화 제안의 단계';h.proposal(next);h.click('ai_apply');await flush();assert.equal(h.forms['ew-stage-editor'],undefined);assert.equal(h.draft().definition.nodes.t0.name,'대화 제안의 단계');assert.equal(h.writes.length,0);
 h.click('stage_edit',{id:'t0'});await flush();h.field('description','아직 적용 안 한 설명');const later=h.draft().definition;later.nodes.t0.name='적용하면 안 되는 제안';h.proposal(later);h.click('ai_apply');await flush();assert.equal(h.fields.find(field=>field.name==='description').value,'아직 적용 안 한 설명');assert.equal(h.draft().definition.nodes.t0.name,'대화 제안의 단계');assert.match(h.markup,/편집 중인 항목을 먼저 적용하거나 취소/);assert.equal(h.writes.length,0);
});
test('changed inline stage form blocks stage job add and menu actions until apply or cancel',async()=>{
 for(const [action,data] of [['stage_toggle',{id:'t1'}],['node',{id:'j0-0'}],['add_stage',{}],['add_job',{parent:'t0'}],['job_menu',{id:'j0-0'}],['stage_menu',{id:'t0'}]]){
  const h=harness();installDefinition(h,stagedDefinition());h.click('stage_toggle',{id:'t0'});h.click('stage_edit',{id:'t0'});await flush();h.field('name','아직 적용 안 함');h.scroll.scrollTop=777;const before=h.draft();h.click(action,data);await flush();
  assert.match(h.markup,/편집 중인 항목을 먼저 적용하거나 취소해 주세요./);assert.equal(h.fields.find(field=>field.name==='name').value,'아직 적용 안 함');assert.equal(h.document.activeElement,h.forms['ew-stage-editor'].controls.find(field=>field.name==='name'));assert.equal(h.scrollRequests?.length,1);assert.equal(h.scrollRequests[0].node,h.forms['ew-stage-editor'].inlineError);assert.deepEqual(copy(h.scrollRequests[0].options),{block:'nearest',inline:'nearest',behavior:'instant'});assert.deepEqual(h.draft(),before);assert.equal(stageButton(h,'t0').getAttribute('aria-expanded'),'true');assert.equal(h.writes.length,0);
  h.click('inline_cancel');await flush();assert.equal(h.draft().dirty,false);assert.equal(h.draft().definition.nodes.t0.name,'단계 1');
 }
});
test('unchanged inline form closes on navigation while Escape cancels changed values',async()=>{
 const h=harness();installDefinition(h,stagedDefinition());h.click('stage_toggle',{id:'t0'});h.click('stage_edit',{id:'t0'});await flush();h.click('node',{id:'j0-0'});await flush();assert.equal(h.forms['ew-stage-editor'],undefined);assert.ok(h.forms['ew-author-node']);
 h.click('node',{id:''});h.click('stage_edit',{id:'t0'});await flush();h.field('description','취소할 첫 줄\n둘째 줄');const result=h.escape('#ew-stage-editor');await flush();assert.equal(result.handled,true);assert.equal(result.preventDefault,true);assert.equal(h.forms['ew-stage-editor'],undefined);assert.equal(h.draft().definition.nodes.t0.description,'첫 줄\n둘째 줄');assert.equal(h.draft().dirty,false);
});
test('stage and job creation require names and retain existing add defaults without writes',async()=>{
 const h=harness();installDefinition(h,stagedDefinition(0));const expected={description:'',instructions:'',children:[],mode:'human',inputs:[],result_block:'human_confirm',deps:[],human_confirmation:true,completion:{rule:''}};
 h.click('add_stage');await flush();assert.equal(Object.values(h.draft().definition.nodes).length,1);h.click('inline_apply');await flush();assert.match(h.markup,/class="ew-inline-error"/);assert.match(h.markup,/단계 이름을 입력해 주세요./);assert.equal(Object.values(h.draft().definition.nodes).length,1);
 await h.inline('  운영 인계  ');const stage=Object.values(h.draft().definition.nodes).find(node=>node.type==='t');assert.deepEqual(stage,{id:stage.id,type:'t',parent:'p',name:'운영 인계',...expected});assert.deepEqual(h.draft().definition.nodes.p.children,[stage.id]);assert.equal(stageButton(h,stage.id).getAttribute('aria-expanded'),'true');assert.equal(h.document.activeElement.dataset.authorAction,'add_job');assert.equal(h.document.activeElement.dataset.parent,stage.id);assert.match(h.markup,/아직 작업이 없습니다/);
 h.click('add_job',{parent:stage.id});await flush();assert.equal(Object.values(h.draft().definition.nodes).filter(node=>node.type==='j').length,0);h.field('name','   ');h.click('inline_apply');await flush();assert.match(h.markup,/작업 이름을 입력해 주세요./);await h.inline('첫 인계 작업');const job=Object.values(h.draft().definition.nodes).find(node=>node.type==='j');assert.deepEqual(job,{id:job.id,type:'j',parent:stage.id,name:'첫 인계 작업',...expected});assert.deepEqual(h.draft().definition.nodes[stage.id].children,[job.id]);assert.ok(h.forms['ew-author-node']);assert.equal(h.draft().dirty,true);assert.equal(h.writes.length,0);
});
test('stage and job ordering targets explicit IDs and preserves parents deadlines expansion and focus',async()=>{
 const h=harness(),value=stagedDefinition(3,3);value.schedule={stage_deadlines:{t0:{offset_days:-2},t1:{offset_days:0},t2:{offset_days:2}}};installDefinition(h,value);
 h.click('stage_toggle',{id:'t0'});h.click('stage_menu',{id:'t0'});await flush();assert.equal(actionButton(h,'move_up','t0').disabled,true);h.click('stage_toggle',{id:'t2'});h.click('stage_menu',{id:'t2'});await flush();assert.equal(actionButton(h,'move_down','t2').disabled,true);
 h.click('stage_toggle',{id:'t1'});h.click('stage_menu',{id:'t1'});await flush();h.click('move_up',{id:'t1'});await flush();assert.deepEqual(h.draft().definition.nodes.p.children,['t1','t0','t2']);assert.equal(stageButton(h,'t1').getAttribute('aria-expanded'),'true');assert.equal(h.document.activeElement.dataset.id,'t1');assert.equal(h.document.activeElement.dataset.authorAction,'stage_menu');assert.equal(actionButton(h,'stage_menu','t1').getAttribute('aria-expanded'),'false');assert.match(h.markup,/<span class="ew-visually-hidden" data-author-live aria-live="polite" aria-atomic="true">1번째로 옮겼습니다/);assert.doesNotMatch(h.markup,/class="ew-author-note"/);
 h.click('job_menu',{id:'j1-0'});await flush();assert.equal(actionButton(h,'move_up','j1-0').disabled,true);h.click('job_menu',{id:'j1-2'});await flush();assert.equal(actionButton(h,'move_down','j1-2').disabled,true);h.click('move_up',{id:'j1-2'});await flush();const draft=h.draft().definition;assert.deepEqual(draft.nodes.t1.children,['j1-0','j1-2','j1-1']);assert.equal(draft.nodes['j1-2'].parent,'t1');assert.deepEqual(draft.schedule,value.schedule);assert.deepEqual(Object.keys(draft.nodes),Object.keys(value.nodes));assert.equal(stageButton(h,'t1').getAttribute('aria-expanded'),'true');assert.equal(h.writes.length,0);
});
test('stage deletion confirmation lists affected jobs and deadline cleanup only when present',async()=>{
 for(const deadline of [false,true]){const h=harness(),value=stagedDefinition(2,2);if(deadline)value.schedule={stage_deadlines:{t0:{offset_days:-1},t1:{offset_days:1}}};value.nodes['j1-0'].deps=['j0-0'];installDefinition(h,value);h.click('stage_toggle',{id:'t0'});await flush();h.dialogs.push({});h.click('delete_node',{id:'t0'});await flush();const options=h.dialogHistory.at(-1);assert.match(options.html,/단계 1/);assert.match(options.html,/2개/);assert.match(options.html,/작업 1-1/);assert.match(options.html,/작업 1-2/);assert.match(options.html,/게시/);if(deadline)assert.match(options.html,/이 단계의 기간 설정\(실행 방식\)도 함께 지웁니다./);else assert.doesNotMatch(options.html,/기간 설정/);
  const draft=h.draft().definition;assert.equal(draft.nodes.t0,undefined);assert.equal(draft.nodes['j0-0'],undefined);assert.deepEqual(draft.nodes['j1-0'].deps,['j0-0']);if(deadline){assert.equal(Object.hasOwn(draft.schedule.stage_deadlines,'t0'),false);assert.deepEqual(draft.schedule.stage_deadlines.t1,{offset_days:1});}assert.equal(h.writes.length,0);
 }
});
test('returning from a job preserves per-workflow expanded stage scroll dirty draft and row focus',async()=>{
 const h=harness();installDefinition(h,stagedDefinition());h.click('stage_toggle',{id:'t1'});await flush();h.scroll.scrollTop=217;h.click('node',{id:'j1-0'});await flush();h.field('job_guidance','미저장 작업 변경');h.click('node',{id:''});await flush();assert.equal(stageButton(h,'t1').getAttribute('aria-expanded'),'true');assert.equal(h.scroll.scrollTop,217);assert.equal(h.draft().dirty,true);assert.equal(h.draft().definition.nodes['j1-0'].instructions,'미저장 작업 변경');assert.equal(h.document.activeElement.dataset.authorAction,'node');assert.equal(h.document.activeElement.dataset.id,'j1-0');assert.match(h.markup,/data-job-id="j1-0" data-returned="true"/);
 await h.open('q');await h.open('w');assert.equal(stageButton(h,'t1').getAttribute('aria-expanded'),'true');assert.equal(h.scroll.scrollTop,217);assert.equal(h.draft().definition.nodes['j1-0'].instructions,'미저장 작업 변경');h.click('stage_toggle',{id:'t2'});await flush();assert.doesNotMatch(h.markup,/data-returned="true"/);assert.equal(h.writes.length,0);
});
test('read-only content permits expanding and opening jobs without management controls',async()=>{
 const h=harness();installDefinition(h,stagedDefinition());h.state.capabilities.can_author=false;h.state.capabilities.managed_systems=[];h.state.workflow.can_manage=false;h.render();
 h.click('stage_toggle',{id:'t0'});await flush();assert.equal(stageButton(h,'t0').getAttribute('aria-expanded'),'true');
 const managed=['stage_edit','stage_menu','add_stage','add_job','job_menu','move_up','move_down','delete_node','summary_edit'];assert.equal(h.buttons.some(button=>managed.includes(button.dataset.authorAction)),false);assert.match(h.markup,/이 범위를 수정할 담당 권한이 없습니다/);h.click('node',{id:'j0-0'});await flush();assert.ok(h.forms['ew-author-node']);assert.equal(h.draft().dirty,false);assert.equal(h.writes.length,0);
});
// Six changes: delete 1, add 2, rename 1, adjacent swap 1, settings 1.
// The former eight also counted a deletion-induced shift and both sides of a swap.
test('proposal changes are computed locally with deletions first and settings counts without raw JSON',async()=>{
 const h=harness(),value=stagedDefinition(2,2);installDefinition(h,value);const proposal=copy(value);delete proposal.nodes['j0-0'];proposal.nodes.t0.children=['j0-1'];proposal.nodes['j0-1'].name='변경된 작업 이름';proposal.nodes['j0-1'].instructions='제안된 수행 안내';proposal.nodes.t1.children.reverse();proposal.nodes.t2={id:'t2',type:'t',parent:'p',children:['j2-0'],name:'추가 단계',deps:[]};proposal.nodes['j2-0']={...copy(value.nodes['j0-0']),id:'j2-0',parent:'t2',name:'추가 작업'};proposal.nodes.p.children.push('t2');const diff=copy(h.helpers.proposalChanges(value,proposal));assert.equal(diff.otherCount,1);assert.equal(diff.count,6);assert.equal(diff.changes.filter(change=>change.kind==='added').length,2);assert.equal(diff.changes.filter(change=>change.kind==='removed').length,1);assert.equal(diff.changes[0].kind,'removed');assert.equal(diff.marks.t0,'changed');assert.equal(diff.marks['j0-1'],'changed');h.proposal(proposal);
 assert.match(h.markup,/업무 도우미 제안 · 반영 전/);assert.match(h.markup,/바뀌는 것/);assert.match(h.markup,/삭제/);assert.match(h.markup,/추가/);assert.match(h.markup,/변경된 작업 이름/);assert.match(h.markup,/그 밖의 설정 1곳/);assert.match(h.markup,/업무 도우미 수정 제안 · 6곳/);assert.doesNotMatch(h.markup,/<pre|&quot;nodes&quot;|&quot;instructions&quot;/);assert.ok(h.markup.indexOf('삭제')<h.markup.indexOf('추가 단계'));assert.equal(h.buttons.filter(button=>button.dataset.authorAction==='ai_discard').length,1);assert.equal(h.buttons.filter(button=>button.dataset.authorAction==='ai_apply').length,1);assert.deepEqual(h.draft().definition,value);assert.equal(h.writes.length,0);
 h.click('stage_toggle',{id:'t0'});await flush();assert.match(h.markup,/바뀜|삭제/);h.click('ai_apply');await flush();assert.deepEqual(h.draft().definition,proposal);assert.equal(h.draft().dirty,true);assert.equal(h.writes.length,0);
});


test('read-only authoring hides header footer and legacy node management actions',async()=>{
 const h=harness(),value=stagedDefinition(1,1);value.nodes.t0.instructions='기존 수행 안내';value.nodes.t0.inputs=[{id:'stage-input',name:'단계 입력',type:'text'}];value.nodes['j0-0'].inputs=[{id:'job-input',name:'작업 입력',type:'text'}];value.nodes['j0-0'].skills=['opaque-skill'];installDefinition(h,value);
 h.state.capabilities.can_author=false;h.state.capabilities.managed_systems=[];h.state.workflow.can_manage=false;h.render();
 const managed=['edit_workflow','copy','save','validate','publish','stage_edit','add_stage','add_job','job_menu','delete_node','move_up','move_down','input_add','input_edit','input_delete','start_input_add','start_input_edit','start_input_delete','summary_edit','summary_optional','factory_settings','skill_remove','pick_job_tool'];
 const absent=()=>assert.deepEqual(h.buttons.filter(button=>managed.includes(button.dataset.authorAction)).map(button=>button.dataset.authorAction),[]);
 absent();assert.doesNotMatch(h.markup,/class="ew-procedure-menu"/);h.click('stage_toggle',{id:'t0'});await flush();absent();await h.node('t0');assert.match(h.markup,/단계 이름/);absent();await h.node('j0-0');absent();h.click('summary_open');await flush();absent();assert.deepEqual(h.draft().definition,value);assert.equal(h.writes.length,0);
});
test('stage delete confirmation cannot mutate after author permission is revoked',async()=>{
 const h=harness(),value=stagedDefinition(2,2);value.schedule={stage_deadlines:{t0:{offset_days:-2},t1:{offset_days:1}}};installDefinition(h,value);h.click('stage_toggle',{id:'t0'});await flush();h.dialogs.push({});
 h.dialogHook=()=>{h.state.capabilities.can_author=false;h.state.capabilities.managed_systems=[];h.state.workflow.can_manage=false;h.render();};h.click('delete_node',{id:'t0'});await flush();assert.equal(h.dialogHistory.length,1);assert.equal(h.designer.canAuthor(),false);assert.deepEqual(h.draft().definition,value);assert.equal(h.draft().dirty,false);assert.equal(h.writes.length,0);
});
test('proposal comparison counts root names node types and replaced roots as settings changes',()=>{
 const h=harness(),before=stagedDefinition(1,1);for(const change of ['root-name','node-type','root-replacement']){const after=copy(before);if(change==='root-name')after.nodes.p.name='바뀐 절차 노드 이름';else if(change==='node-type')after.nodes['j0-0'].type='t';else{after.nodes.newRoot={...after.nodes.p,id:'newRoot'};delete after.nodes.p;after.nodes.t0.parent='newRoot';}
  const diff=copy(h.helpers.proposalChanges(before,after));assert.ok(diff.count>0,change);assert.ok(diff.otherCount>0,change);assert.ok(diff.changes.some(row=>row.details?.length),change);assert.deepEqual(before,stagedDefinition(1,1));
 }
});
test('unapplied business purpose edit blocks proposal application and preserves its buffer',async()=>{
 const h=harness();h.proposal({...definition(),description:'대화 제안 목적'});h.click('summary_edit',{id:'business'});await flush();h.field('description','직접 편집 중인 목적');h.click('ai_apply');await flush();assert.match(h.markup,/편집 중인 항목을 적용하거나 취소/);assert.equal(h.fields.find(field=>field.name==='description').value,'직접 편집 중인 목적');assert.equal(h.draft().definition.description,undefined);assert.equal(h.buttons.some(button=>button.dataset.authorAction==='ai_apply'),true);assert.equal(h.writes.length,0);
 h.click('summary_cancel');h.click('ai_apply');await flush();assert.equal(h.draft().definition.description,'대화 제안 목적');assert.equal(h.draft().dirty,true);assert.equal(h.writes.length,0);
});
test('stage help supplies both exact paragraphs to the shared help dialog',async()=>{
 const h=harness();h.click('help',{id:'stages_and_jobs'});await flush();assert.equal(h.helpCalls.length,1);const call=h.helpCalls[0],term=call.help.terms.find(term=>term.id==='stages_and_jobs');assert.equal(call.termId,'stages_and_jobs');assert.equal(term.name,'단계와 작업');assert.equal(term.summary,'단계는 작업을 묶는 이름입니다. 개수·이름·순서는 업무에 맞게 정합니다.\n\n단계와 작업은 적힌 순서대로 진행합니다. 기존에 정한 적용 조건과 작업 연결은 유지됩니다.');assert.equal(h.draft().dirty,false);assert.equal(h.writes.length,0);
});


test('proposal other settings initially collapse with counts and retain only their own disclosure state',async()=>{
 const h=harness();const menu=h.host.querySelector('.ew-procedure-menu');menu.open=true;h.render();const proposed=definition();proposed.nodes.j.instructions='첫 수행 안내 제안';h.proposal(proposed);
 assert.match(h.markup,/<div class="ew-proposal-changes"><h3>바뀌는 것 1<\/h3>/);let other=h.host.querySelector('.ew-proposal-other');assert.ok(other);assert.equal(other.open,false);assert.match(h.markup,/<details class="ew-proposal-other"[^>]*><summary>[\s\S]*?그 밖의 설정 1곳/);assert.match(h.markup,/확인 작업 › 수행 안내/);assert.match(h.markup,/업무 도우미 수정 제안 · 1곳/);
 other.open=true;h.render();other=h.host.querySelector('.ew-proposal-other');assert.equal(other.open,true);assert.match(h.markup,/그 밖의 설정 1곳/);assert.equal(h.draft().dirty,false);
 const next=definition();next.nodes.j.instructions='두 번째 제안';next.description='업무 목적 제안';h.proposal(next);other=h.host.querySelector('.ew-proposal-other');assert.equal(other.open,false);assert.match(h.markup,/바뀌는 것 2/);assert.match(h.markup,/그 밖의 설정 2곳/);assert.match(h.markup,/업무 도우미 수정 제안 · 2곳/);assert.equal(h.writes.length,0);
});


test('proposal deletion and front insertion do not mark unchanged surviving siblings',async()=>{
 const h=harness(),before=stagedDefinition(4,3);installDefinition(h,before);
 const removed=copy(before);for(const id of ['t0',...before.nodes.t0.children])delete removed.nodes[id];removed.nodes.p.children.shift();
 const diff=copy(h.helpers.proposalChanges(before,removed));assert.equal(diff.count,4);assert.equal(diff.changes.length,1);assert.equal(diff.changes[0].kind,'removed');assert.match(diff.changes[0].text,/작업 1-1.*작업 1-2.*작업 1-3/);
 for(const id of ['t1','t2','t3'])assert.equal(diff.marks[id],undefined);
 h.proposal(removed);assert.match(h.markup,/바뀌는 것 4/);for(const id of ['t1','t2','t3']){const row=h.markup.match(new RegExp('<section class="ew-content-stage" data-stage-id="'+id+'">([\\s\\S]*?)<\\/section>'))?.[1];assert.ok(row);assert.doesNotMatch(row,/ew-proposal-mark/);}
 const added=copy(before);added.nodes.front={id:'front',type:'t',name:'맨 앞 단계',parent:'p',children:[],deps:[]};added.nodes.p.children.unshift('front');
 const insertion=copy(h.helpers.proposalChanges(before,added));assert.equal(insertion.count,1);assert.equal(insertion.changes.length,1);assert.equal(insertion.changes[0].kind,'added');assert.equal(insertion.marks.t0,undefined);
});

test('proposal moves use an LCS of common siblings and count a parent move once',()=>{
 const h=harness(),before=stagedDefinition(2,3),swapped=copy(before);swapped.nodes.t0.children=['j0-1','j0-0','j0-2'];
 const diff=copy(h.helpers.proposalChanges(before,swapped));assert.equal(diff.count,1);assert.equal(diff.changes.filter(row=>row.kind==='changed').length,1);
 const moved=copy(before);moved.nodes.t0.children.shift();moved.nodes.t1.children.unshift('j0-0');moved.nodes['j0-0'].parent='t1';
 const parentDiff=copy(h.helpers.proposalChanges(before,moved));assert.equal(parentDiff.count,1);assert.equal(parentDiff.changes[0].id,'j0-0');assert.match(parentDiff.changes[0].text,/단계 2/);
 const arrayBefore={...before,nodes:Object.values(before.nodes)},arrayAfter={...swapped,nodes:Object.values(swapped.nodes)};assert.equal(h.helpers.proposalChanges(arrayBefore,arrayAfter).count,1);
});

test('proposal groups added sibling jobs and orders deletions additions changes and settings',()=>{
 const h=harness(),before=stagedDefinition(2,2),after=copy(before);delete after.nodes['j1-0'];after.nodes.t1.children.shift();after.nodes['j0-0'].name='이름 변경';after.nodes['j0-0'].instructions='설명 변경';
 for(const [id,name] of [['new-a','A'],['new-b','B']]){after.nodes[id]={...copy(before.nodes['j0-0']),id,name,parent:'t1'};after.nodes.t1.children.push(id);}
 const diff=copy(h.helpers.proposalChanges(before,after));assert.equal(diff.count,5);assert.deepEqual(diff.changes.map(row=>row.kind),['removed','added','changed','changed']);assert.equal(diff.changes[1].text,'작업 ‘A’ · ‘B’ — 단계 2');assert.equal(diff.marks['new-a'],'added');assert.equal(diff.marks['new-b'],'added');assert.equal(diff.changes.at(-1).text,'그 밖의 설정 1곳');
});

test('proposal stage deletion warns and cleans deadlines on apply while preserving unsaved and saved definitions',async()=>{
 const h=harness(),before=stagedDefinition(2,2);before.schedule={stage_deadlines:{t0:{offset_days:-1},t1:{offset_days:1}},extension:'preserve'};installDefinition(h,before);
 const after=copy(before);for(const id of ['t0',...before.nodes.t0.children])delete after.nodes[id];after.nodes.p.children.shift();
 h.proposal(after);assert.match(h.markup,/기간 설정도 함께 지웁니다/);assert.deepEqual(h.draft().definition,before);h.click('ai_apply');await flush();
 const draft=h.draft();assert.equal(Object.hasOwn(draft.definition.schedule.stage_deadlines,'t0'),false);assert.deepEqual(draft.definition.schedule.stage_deadlines.t1,{offset_days:1});assert.equal(draft.definition.schedule.extension,'preserve');assert.equal(draft.dirty,true);assert.deepEqual(h.workflows.get('w').draft,before);assert.deepEqual(after.schedule,before.schedule);assert.equal(h.writes.length,0);
});

test('closed job menu does not handle Escape and open menu returns focus to its trigger',async()=>{
 const h=harness();installDefinition(h,stagedDefinition(1,2));h.click('stage_toggle',{id:'t0'});await flush();
 const escape=()=>h.designer.handleEvent({type:'keydown',key:'Escape',target:{closest:selector=>selector==='#ees-work-designer'?h.host:selector==='.ew-job-menu,.ew-job-menu-button'?actionButton(h,'job_menu','j0-0'):null}});
 actionButton(h,'job_menu','j0-0').focus();assert.deepEqual(copy(escape()),{handled:false,preventDefault:false});
 h.click('job_menu',{id:'j0-0'});await flush();assert.deepEqual(copy(escape()),{handled:true,preventDefault:true});assert.doesNotMatch(h.markup,/class="ew-job-menu"/);assert.equal(h.document.activeElement.dataset.authorAction,'job_menu');assert.equal(h.document.activeElement.dataset.id,'j0-0');
});

test('stage reorder updates hidden live text without adding a visible notice and preserves scroll',async()=>{
 const h=harness();installDefinition(h,stagedDefinition(4,2));h.click('stage_toggle',{id:'t1'});await flush();h.scroll.scrollTop=217;
 h.click('stage_menu',{id:'t1'});h.click('move_down',{id:'t1'});await flush();assert.doesNotMatch(h.markup,/class="ew-author-note"/);assert.match(h.markup,/data-author-live aria-live="polite" aria-atomic="true">3번째로 옮겼습니다/);assert.equal(h.scroll.scrollTop,217);assert.equal(h.document.activeElement.dataset.id,'t1');assert.equal(h.document.activeElement.dataset.authorAction,'stage_menu');
 h.click('stage_menu',{id:'t1'});h.click('move_up',{id:'t1'});await flush();assert.match(h.markup,/data-author-live aria-live="polite" aria-atomic="true">2번째로 옮겼습니다/);assert.doesNotMatch(h.markup,/3번째로 옮겼습니다/);
});

test('new stage and job name fields show the Figma examples',async()=>{
 const h=harness();installDefinition(h,stagedDefinition(1,1));h.click('add_stage');await flush();assert.match(h.markup,/name="name"[^>]*placeholder="예: 운영 인계"/);h.click('inline_cancel');await flush();h.click('stage_toggle',{id:'t0'});await flush();h.click('add_job',{parent:'t0'});await flush();assert.match(h.markup,/name="name"[^>]*placeholder="예: 설치 상태 확인"/);
});


test('stage movement skips other kinds in a mixed draft and preserves their slots',async()=>{
 const h=harness(),value=stagedDefinition(2,1);value.nodes.rootJob={...copy(value.nodes['j0-0']),id:'rootJob',parent:'p',name:'단계 밖 초안 작업'};value.nodes.p.children=['t0','rootJob','t1'];installDefinition(h,value);
 h.click('stage_toggle',{id:'t0'});h.click('stage_menu',{id:'t0'});await flush();assert.equal(actionButton(h,'move_down','t0').disabled,false);h.click('move_down',{id:'t0'});await flush();
 assert.deepEqual(h.draft().definition.nodes.p.children,['t1','rootJob','t0']);assert.deepEqual(h.draft().definition.nodes.rootJob,value.nodes.rootJob);assert.match(h.markup,/data-author-live[^>]*>2번째로 옮겼습니다/);assert.equal(h.document.activeElement.dataset.authorAction,'stage_menu');assert.equal(actionButton(h,'stage_menu','t0').getAttribute('aria-expanded'),'false');
 h.click('stage_menu',{id:'t0'});await flush();assert.equal(actionButton(h,'move_down','t0').disabled,true);h.click('move_up',{id:'t0'});await flush();assert.deepEqual(h.draft().definition.nodes.p.children,value.nodes.p.children);assert.match(h.markup,/data-author-live[^>]*>1번째로 옮겼습니다/);assert.equal(h.writes.length,0);
});

test('job movement skips other kinds in a mixed draft and keeps endpoints unchanged',async()=>{
 const h=harness(),value=stagedDefinition(1,2);value.nodes.mixed={id:'mixed',type:'t',name:'초안 구조 확인 대상',parent:'t0',children:[],deps:[]};value.nodes.t0.children=['j0-0','mixed','j0-1'];installDefinition(h,value);
 h.click('stage_toggle',{id:'t0'});await flush();h.click('job_menu',{id:'j0-0'});await flush();h.click('move_down',{id:'j0-0'});await flush();assert.deepEqual(h.draft().definition.nodes.t0.children,['j0-1','mixed','j0-0']);assert.deepEqual(h.draft().definition.nodes.mixed,value.nodes.mixed);assert.equal(h.document.activeElement.dataset.authorAction,'job_menu');assert.equal(actionButton(h,'job_menu','j0-0').getAttribute('aria-expanded'),'false');h.click('job_menu',{id:'j0-0'});await flush();assert.equal(actionButton(h,'move_down','j0-0').disabled,true);
 h.click('move_down',{id:'j0-0'});await flush();assert.deepEqual(h.draft().definition.nodes.t0.children,['j0-1','mixed','j0-0']);assert.equal(h.writes.length,0);
});

test('one proposal comparison feeds all 248 job marks list and footer per paint',async t=>{
 let comparisons=0;const h=harness({proposalChangesObserver:()=>comparisons++}),value=stagedDefinition(1,248);installDefinition(h,value);h.click('stage_toggle',{id:'t0'});await flush();
 const after=copy(value);after.nodes['j0-2'].name='대화에서 바꾼 이름';comparisons=0;const start=process.hrtime.bigint();h.proposal(after);const elapsedMs=Number(process.hrtime.bigint()-start)/1e6;
 t.diagnostic(JSON.stringify({nodes:Object.keys(value.nodes).length,jobs:248,comparisons,elapsedMs}));
 assert.equal((h.markup.match(/class="ew-job-row"/g)||[]).length,248);assert.match(h.markup,/바뀌는 것 1/);assert.match(h.markup,/업무 도우미 수정 제안 · 1곳/);assert.match(h.markup,/data-job-id="j0-2"[\s\S]*?<small class="ew-proposal-mark" data-change="changed">바뀜/);
 assert.equal((h.markup.match(/<small class="ew-proposal-mark"/g)||[]).length,2);assert.equal(comparisons,1);
 const markup=h.markup;comparisons=0;h.render();assert.equal(comparisons,1);assert.equal(h.markup,markup);
 h.click('ai_discard');await flush();comparisons=0;h.render();assert.equal(comparisons,0);assert.doesNotMatch(h.markup,/ew-proposal-mark/);
});


test('an existing stage with empty advanced values can open its full editor',async()=>{
 const h=harness(),value=stagedDefinition(1,1);installDefinition(h,value);h.click('stage_toggle',{id:'t0'});await flush();h.click('stage_edit',{id:'t0'});await flush();
 assert.ok(h.host.querySelector('.ew-stage-advanced'));assert.match(h.markup,/추가 설정 수정/);assert.doesNotMatch(h.markup,/수행 안내 있음|사람이 정하는 값 있음/);assert.ok(actionButton(h,'node','t0'));
 h.click('node',{id:'t0'});await flush();assert.ok(h.forms['ew-author-node']);assert.ok(h.fields.find(field=>field.name==='instructions'));assert.equal(h.draft().dirty,false);assert.deepEqual(h.draft().definition,value);assert.equal(h.writes.length,0);
});

test('empty stage advanced entry preserves unapplied names and stays absent on new stage forms',async()=>{
 const h=harness(),value=stagedDefinition(1,1);installDefinition(h,value);h.click('stage_toggle',{id:'t0'});await flush();h.click('stage_edit',{id:'t0'});await flush();assert.ok(actionButton(h,'node','t0'));
 h.field('name','미적용 단계 이름');h.field('description','미적용 설명');h.click('node',{id:'t0'});await flush();assert.ok(h.forms['ew-stage-editor']);assert.equal(h.forms['ew-author-node'],undefined);assert.match(h.markup,/편집 중인 항목을 먼저 적용하거나 취소해 주세요/);assert.equal(h.fields.find(field=>field.name==='name').value,'미적용 단계 이름');assert.equal(h.fields.find(field=>field.name==='description').value,'미적용 설명');assert.deepEqual(h.draft().definition,value);
 h.click('inline_apply');await flush();h.click('stage_edit',{id:'t0'});await flush();h.click('node',{id:'t0'});await flush();assert.ok(h.forms['ew-author-node']);assert.equal(h.draft().definition.nodes.t0.name,'미적용 단계 이름');assert.equal(h.draft().definition.nodes.t0.description,'미적용 설명');assert.equal(h.writes.length,0);
 h.click('node',{id:''});await flush();h.click('add_stage');await flush();assert.equal(h.host.querySelector('.ew-stage-advanced'),null);assert.doesNotMatch(h.markup,/추가 설정 수정/);
});

test('proposal ordinals count only same kind siblings without changing LCS counts',()=>{
 const h=harness(),before=stagedDefinition(2,1);before.nodes.rootJob={...copy(before.nodes['j0-0']),id:'rootJob',parent:'p',name:'단계 밖 초안 작업'};before.nodes.p.children=['t0','rootJob','t1'];
 const moved=copy(before);moved.nodes.p.children=['t1','rootJob','t0'];const move=copy(h.helpers.proposalChanges(before,moved));assert.equal(move.count,1);assert.equal(move.changes[0].text,'단계 ‘단계 1’ · 2번째');
 const added=copy(before);added.nodes.t2={id:'t2',type:'t',parent:'p',name:'추가 단계',children:[],deps:[]};added.nodes.p.children.push('t2');const addition=copy(h.helpers.proposalChanges(before,added));assert.equal(addition.count,1);assert.equal(addition.changes[0].text,'단계 ‘추가 단계’ (3번째)');
 const jobBefore=stagedDefinition(1,2);jobBefore.nodes.mixed={id:'mixed',type:'t',parent:'t0',name:'초안 구조 확인 대상',children:[],deps:[]};jobBefore.nodes.t0.children=['j0-0','mixed','j0-1'];const jobAfter=copy(jobBefore);jobAfter.nodes.t0.children=['j0-1','mixed','j0-0'];const jobMove=copy(h.helpers.proposalChanges(jobBefore,jobAfter));assert.equal(jobMove.count,1);assert.equal(jobMove.changes[0].text,'작업 ‘작업 1-1’ · 2번째');
});

function c66LegacyTool(h,schema={type:'object',properties:{target:{type:'string'},limit:{type:'integer',minimum:1,maximum:100}},required:['target']}){
 const tool={id:'legacy',name:'기존 확인 도구',description:'확인 대상을 조회합니다.',state:'approved',revision:3,kind:'read',reference:{tool_id:'private-tool',function:'read',content_hash:'keep'},input_schema:copy(schema)};
 h.state.operations={tools:[tool],shared_tools:[]};return tool;
}
async function a12Open(h,candidate){h.click('job_tool_setup');await flush();assert.ok(h.modal,'the actual setup action opens a dialog');if(candidate!==undefined){h.modalCandidate(candidate);await flush();}}
async function a12Connect(h,id,{shared=true,values={},runtime=true}={}){
 if(h.draft().definition.nodes.j.mode!=='tool'){h.field('mode','tool','change');await flush();}
 await a12Open(h,(shared?'shared:':'legacy:')+id);
 if(runtime)for(const control of [...h.modal.querySelectorAll('[data-job-tool-runtime]')])h.modalField('data-job-tool-runtime',control.dataset.jobToolRuntime,true,'change');
 for(const [key,value] of Object.entries(values)){const runtime=h.modal.querySelector('[data-job-tool-runtime="'+key+'"]');if(runtime?.checked)h.modalField('data-job-tool-runtime',key,false,'change');h.modalField('data-job-tool-value',key,value);}
 await h.modalClose('apply');
}
async function c66SelectShared(h){sharedReviewFixture(h);h.render();await h.node();await a12Connect(h,'managed-search_pages');}
async function a12Clear(h){h.dialogs.push({});h.field('mode','human','change');await flush();h.field('mode','tool','change');await flush();}
const c66Section=(h,id)=>actionButton(h,'job_section',id);
const c66Argument=(h,id)=>actionButton(h,'job_argument',id);
function a12ConnectedMarkup(h){return h.markup.match(/<div class="ew-job-connected-tool"[^>]*>([\s\S]*?)<\/div>/)?.[1]||h.markup;}

for(const [mode,resultBlock] of [['human','human_confirm'],['ai','human_confirm'],['tool','human_confirm'],['tool','change_request']])test('A12 hidden legacy settings survive inspection and an unrelated save: '+mode+' '+resultBlock,async()=>{
 const h=harness(),value=definition();Object.assign(value.nodes.j,{mode,result_block:resultBlock,instructions:'원래 안내',description:'별도 설명',deps:['missing'],condition:{all:[{field:'factory_id',op:'eq',value:'f'}]},deadline:{input:'when',offset_days:-2,extension:'keep'},trigger:{offset_seconds:30},read_retry:{count:2,deadline_seconds:45,extension:'보존'},skills:['private-skill'],extension:{keep:true}});installDefinition(h,value);await h.node();
 assert.doesNotMatch(h.markup,/data-author-action="job_section"[^>]*data-id="advanced"/);assert.equal(h.fields.some(f=>f.name==='description'||f.name==='read_retry_count'||f.name==='deadline_notes'),false);assert.equal(h.fields.find(f=>f.name==='job_guidance').value,'원래 안내\n\n별도 설명');assert.deepEqual(h.draft().definition,value);assert.equal(h.draft().dirty,false);
 h.field('name','이름만 수정');h.click('save');await flush();const expected=copy(value);expected.nodes.j.name='이름만 수정';assert.deepEqual(h.writes[0].definition,expected);assert.equal(h.operations.length,0);
});
for(const [instructions,description,shown] of [['안내','설명','안내\n\n설명'],['같은 글','같은 글','같은 글'],['','설명','설명']])test('A12 merged guidance preserves originals until an actual edit: '+JSON.stringify([instructions,description]),async()=>{
 const h=harness(),value=definition();Object.assign(value.nodes.j,{instructions,description});installDefinition(h,value);await h.node();assert.equal(h.fields.find(f=>f.name==='job_guidance').value,shown);h.field('job_guidance',shown);h.render();assert.deepEqual(h.draft().definition,value);assert.equal(h.draft().dirty,false);
 h.field('job_guidance','수정한 전체 안내');h.click('save');await flush();assert.equal(h.writes[0].definition.nodes.j.instructions,'수정한 전체 안내');assert.equal(h.writes[0].definition.nodes.j.description,'');await h.open('q');await h.open('w');await h.node();assert.equal(h.fields.find(f=>f.name==='job_guidance').value,'수정한 전체 안내');
});
test('A12 connected tool shows its name without a read badge or version pinning',async()=>{
 const h=harness(),{search}=sharedReviewFixture(h),value=definition();search.version=7;Object.assign(value.nodes.j,{mode:'tool',shared_tool_id:search.id,inputs:[{id:'query',name:'검색어',type:'text',scope:'factory'}],argument_bindings:{query:{input:'query'}}});installDefinition(h,value);await h.node();
 assert.match(h.markup,/연결된 도구/);assert.doesNotMatch(h.markup,/쓰는 도구|>조회<|class="ew-shared-picker"|도구에 넣을 값/);assert.match(h.markup,/Confluence 페이지 찾기/);assert.doesNotMatch(h.markup,/>v7</);search.version=8;h.render();assert.doesNotMatch(h.markup,/>v[78]</);assert.deepEqual(h.draft().definition,value);assert.equal(h.draft().dirty,false);
});
test('A12 setup stages candidates and input edits until explicit apply and isolates other workflows',async()=>{
 const h=harness();await c66SelectShared(h);const before=h.draft(),other=copy(h.workflows.get('q').draft);await a12Open(h,'shared:managed-get_page');h.modalField('data-job-tool-value','page_id','12345');assert.deepEqual(h.draft(),before);await h.modalClose('apply');const node=h.draft().definition.nodes.j;assert.equal(node.shared_tool_id,'managed-get_page');assert.deepEqual(node.argument_bindings.page_id,{constant:'12345'});assert.equal(node.human_confirmation,true);assert.deepEqual(h.workflows.get('q').draft,other);assert.equal(h.writes.length,0);
});
for(const close of ['cancel','escape'])test('A12 '+close+' discards pending candidate and values while preserving dirty state',async()=>{
 const h=harness();await c66SelectShared(h);h.click('save');await flush();const before=h.draft();await a12Open(h,'shared:managed-get_page');h.modalField('data-job-tool-value','page_id','discard-me');await h.modalClose(close);assert.deepEqual(h.draft(),before);assert.equal(h.writes.length,1);assert.equal(h.document.activeElement?.dataset.authorAction,'job_tool_setup');
});
test('A12 unchanged same-tool apply preserves all raw values without dirtying the draft',async()=>{
 const h=harness(),{read}=sharedReviewFixture(h),value=definition();Object.assign(value.nodes.j,{mode:'tool',shared_tool_id:read.id,human_confirmation:false,completion:{rule:'보존할 기준',opaque:true},argument_bindings:{page_id:{constant:' 123 '}},inputs:[],description:'원문 설명'});installDefinition(h,value);await h.node();const before=h.draft();await a12Open(h);await h.modalClose('apply');assert.deepEqual(h.draft(),before);assert.equal(h.writes.length,0);
});
test('A12 unavailable or unknown tool remains visible and cannot silently normalize stored state',async()=>{
 for(const state of ['review_required','disabled','unavailable','missing']){const h=harness(),{search}=sharedReviewFixture(h),value=definition();search.state=state;search.can_use=false;search.unavailable_message='도구 확인 필요';if(state==='missing')h.state.operations.shared_tools=[];Object.assign(value.nodes.j,{mode:'tool',shared_tool_id:search.id,shared_tool_version:5,argument_bindings:{query:{constant:'opaque query'}},inputs:[],human_confirmation:false});installDefinition(h,value);await h.node();const before=h.draft();assert.match(h.markup,/확인 필요|사용.*없|확인해/);await a12Open(h);await h.modalClose('cancel');assert.deepEqual(h.draft(),before);h.field('name','이름만 변경');h.click('save');await flush();const expected=copy(value);expected.nodes.j.name='이름만 변경';assert.deepEqual(h.writes[0].definition,expected);}
});
test('A12 human detail has two real method choices and no duplicate result-confirmation control',async()=>{
 const h=harness();await h.node();assert.match(h.markup,/단계와 작업/);assert.deepEqual(h.fields.filter(f=>f.name==='mode').map(f=>[f.type,f.value,f.checked]),[['radio','human',true],['radio','tool',false]]);assert.match(h.markup,/무엇을 확인하나요|확인 방법|완료 기준/);assert.equal(h.fields.some(f=>f.name==='result_confirmation'),false);assert.equal(h.fields.find(f=>f.name==='name').getAttribute('maxlength'),'160');assert.ok(actionButton(h,'job_menu','j'));assert.equal(h.draft().dirty,false);
});
for(const oldBlock of ['change_request','schedule','list_confirm'])test('A12 human detail preserves older result kinds: '+oldBlock,async()=>{
 const h=harness(),value=definition();value.nodes.j.result_block=oldBlock;value.nodes.j.completion={rule:'기존 완료 기준',opaque:'keep'};installDefinition(h,value);await h.node();assert.equal(h.fields.find(f=>f.name==='result_block').value,oldBlock);h.field('job_guidance','확인 안내만 수정');h.click('save');await flush();assert.equal(h.writes[0].definition.nodes.j.result_block,oldBlock);assert.deepEqual(h.writes[0].definition.nodes.j.completion,value.nodes.j.completion);
});
test('A12 an unconnected tool does not fabricate arguments or a result mode',async()=>{const h=harness();await h.node();h.field('mode','tool','change');await flush();assert.match(h.markup,/도구 연결 전/);assert.ok(actionButton(h,'job_tool_setup'));assert.equal(h.fields.some(f=>f.name==='result_confirmation'),false);assert.equal(h.draft().definition.nodes.j.shared_tool_id,undefined);assert.equal(h.writes.length,0);});
test('A12 legacy AI settings remain editable and preserved without offering new AI work',async()=>{
 const h=harness(),value=definition();Object.assign(value.nodes.j,{mode:'ai',result_block:'ai_review',completion:{kind:'delivery',rule:'송부 근거 확인',extra:true},dependency_policy:'all_resolved',skills:['private-skill'],human_confirmation:false});installDefinition(h,value);await h.node();assert.equal(h.fields.some(f=>f.name==='mode'&&f.value==='ai'),false);assert.match(h.markup,/기존 AI 작업/);h.field('job_guidance','AI 안내만 변경');h.click('save');await flush();const saved=h.writes[0].definition.nodes.j;assert.equal(saved.mode,'ai');assert.deepEqual(saved.completion,value.nodes.j.completion);assert.equal(saved.dependency_policy,'all_resolved');assert.deepEqual(saved.skills,['private-skill']);assert.equal(saved.human_confirmation,false);
});
test('A12 D5 cancel and confirm preserve manual fields and clean only generated tool data',async()=>{
 const h=harness();h.workflows.get('w').draft.nodes.j.inputs=[{id:'manual',name:'직접 만든 값',type:'text',scope:'factory',custom:{keep:true}}];await c66SelectShared(h);const original=h.draft().definition;h.dialogs.push(null);h.field('mode','human','change');await flush();assert.deepEqual(h.draft().definition,original);h.dialogs.push({});h.field('mode','human','change');await flush();const node=h.draft().definition.nodes.j;assert.equal(node.mode,'human');assert.equal(node.shared_tool_id,undefined);assert.equal(node.shared_tool_generated,undefined);assert.deepEqual(node.inputs,[original.nodes.j.inputs.find(f=>f.id==='manual')]);assert.deepEqual(node.argument_bindings||{},{});assert.equal(node.instructions,original.nodes.j.instructions);assert.equal(h.writes.length,0);
});
test('A12 D5 preserves manually customized generated bindings',async()=>{
 const h=harness();await c66SelectShared(h);const value=h.draft().definition;value.nodes.j.argument_bindings.query={constant:'사람이 고친 검색어'};value.nodes.j.inputs.push({id:'manual',name:'개인 입력',type:'text',scope:'run'});h.designer.reset();installDefinition(h,value);await h.node();h.dialogs.push({});h.field('mode','human','change');await flush();assert.deepEqual(h.draft().definition.nodes.j.argument_bindings.query,{constant:'사람이 고친 검색어'});assert.ok(h.draft().definition.nodes.j.inputs.some(f=>f.id==='manual'));
});
test('A12 runtime input scope roundtrips and existing factory scope is preserved',async()=>{
 const h=harness();await c66SelectShared(h);await a12Open(h);h.modalField('data-job-tool-scope','query',true,'change');await h.modalClose('apply');let node=h.draft().definition.nodes.j;assert.deepEqual(node.argument_bindings.query,{input:'query'});assert.equal(node.inputs.find(f=>f.id==='query').scope,'workflow');h.click('save');await flush();await h.open('q');await h.open('w');await h.node();assert.equal(h.draft().definition.nodes.j.inputs.find(f=>f.id==='query').scope,'workflow');
 const value=h.draft().definition;value.nodes.j.inputs.find(f=>f.id==='query').scope='factory';h.designer.reset();installDefinition(h,value);await h.node();await a12Open(h);const scope=h.modal.querySelector('[data-job-tool-scope="query"]');assert.ok(!scope||scope.disabled);await h.modalClose('apply');assert.deepEqual(h.draft().definition,value);
});
test('A12 invalid numeric answers never change the original binding and block explicit apply',async()=>{
 const h=harness();await c66SelectShared(h);const before=h.draft();await a12Open(h);h.modalField('data-job-tool-runtime','limit',false,'change');h.modalField('data-job-tool-value','limit','not a number');assert.equal(await h.modalClose('apply'),false);assert.deepEqual(h.draft(),before);assert.match(h.modalMarkup,/ew-workflow-tool-error/);assert.equal(h.modal.querySelector('[data-job-tool-value="limit"]').value,'not a number');h.modalField('data-job-tool-value','limit','13');await h.modalClose('apply');assert.deepEqual(h.draft().definition.nodes.j.argument_bindings.limit,{constant:13});h.click('save');await flush();assert.deepEqual(h.writes[0].definition.nodes.j.argument_bindings.limit,{constant:13});
});
test('A12 required empty constant blocks apply while optional defaults are not silently pinned',async()=>{
 const h=harness();sharedReviewFixture(h);h.render();await h.node();h.field('mode','tool','change');await flush();const before=h.draft();await a12Open(h,'shared:managed-search_pages');assert.equal(await h.modalClose('apply'),false);assert.deepEqual(h.draft(),before);h.modalField('data-job-tool-value','query','목업');await h.modalClose('apply');assert.deepEqual(h.draft().definition.nodes.j.argument_bindings.query,{constant:'목업'});assert.equal(h.writes.length,0);
});
test('A12 candidate switching keeps per-candidate edits and applies only the final choice',async()=>{
 const h=harness();await c66SelectShared(h);const before=h.draft();await a12Open(h,'shared:managed-get_page');h.modalField('data-job-tool-value','page_id','page-draft');h.modalCandidate('shared:managed-search_pages');h.modalCandidate('shared:managed-get_page');assert.equal(h.modal.querySelector('[data-job-tool-value="page_id"]').value,'page-draft');assert.deepEqual(h.draft(),before);await h.modalClose('apply');assert.deepEqual(Object.keys(h.draft().definition.nodes.j.argument_bindings),['page_id']);
});
test('A12 list confirmation is mandatory; automatic read can change without losing its criterion',async()=>{
 const h=harness();await c66SelectShared(h);assert.equal(h.fields.find(f=>f.name==='result_confirmation'&&f.value==='automatic').disabled,true);const before=h.draft();h.field('result_confirmation','automatic','change');assert.deepEqual(h.draft(),before);
 await a12Connect(h,'managed-get_page',{runtime:false,values:{page_id:'123'}});h.field('completion_rule','사람이 확인할 원래 기준');h.field('result_confirmation','automatic','change');await flush();assert.equal(h.draft().definition.nodes.j.human_confirmation,false);assert.equal(h.draft().definition.nodes.j.completion.rule,'사람이 확인할 원래 기준');assert.equal(h.fields.some(f=>f.name==='completion_rule'),false);h.field('result_confirmation','manual','change');await flush();assert.equal(h.fields.find(f=>f.name==='completion_rule').value,'사람이 확인할 원래 기준');assert.equal(h.draft().definition.nodes.j.human_confirmation,true);
});
test('A12 changing only same-tool values preserves the saved automatic result mode',async()=>{
 const h=harness();await c66SelectShared(h);await a12Connect(h,'managed-get_page',{runtime:false,values:{page_id:'123'}});h.field('result_confirmation','automatic','change');await flush();await a12Open(h);h.modalField('data-job-tool-value','page_id','456');await h.modalClose('apply');assert.equal(h.draft().definition.nodes.j.human_confirmation,false);assert.deepEqual(h.draft().definition.nodes.j.argument_bindings.page_id,{constant:'456'});
});
test('A12 an explicit tool replacement retains compatible bindings and manual metadata, resetting only changed argument types',async()=>{
 const h=harness(),tool=c66LegacyTool(h,{properties:{kept:{type:'string'},changed:{type:'string'},removed:{type:'string'}}}),next={...copy(tool),id:'other',name:'다른 도구',reference:{tool_id:'other',function:'read'},input_schema:{properties:{kept:{type:'string'},changed:{type:'integer'}}}},value=definition();h.state.operations.tools.push(next);
 Object.assign(value.nodes.j,{mode:'tool',tool_contract_id:tool.id,tool_reference:copy(tool.reference),argument_bindings:{kept:{input:'manual',extension:'keep'},changed:{constant:'old'},removed:{constant:'prior'}},inputs:[{id:'manual',name:'직접 만든 입력',type:'text',scope:'factory',opaque:{keep:true}}],description:'기존 설명',completion:{rule:'담당자 확인 기준',opaque:true},assignee:{kind:'user',id:'owner'},human_confirmation:false});installDefinition(h,value);await h.node();await a12Open(h,'legacy:other');assert.deepEqual(h.draft().definition,value);h.modalField('data-job-tool-value','changed','12');await h.modalClose('apply');const node=h.draft().definition.nodes.j;
 assert.equal(node.tool_contract_id,'other');assert.deepEqual(node.argument_bindings,{kept:value.nodes.j.argument_bindings.kept,changed:{constant:12}});assert.deepEqual(node.inputs,value.nodes.j.inputs);assert.equal(node.description,'기존 설명');assert.deepEqual(node.completion,value.nodes.j.completion);assert.deepEqual(node.assignee,value.nodes.j.assignee);assert.equal(node.human_confirmation,true);assert.equal(h.writes.length,0);
});
for(const mode of ['human','tool','ai'])test('A12 read-only detail exposes saved values and blocks all mutation: '+mode,async()=>{
 const h=harness(),value=definition();value.nodes.j.mode=mode;value.nodes.j.instructions='보존할 수행 안내';if(mode==='tool'){const tool=c66LegacyTool(h);Object.assign(value.nodes.j,{tool_contract_id:tool.id,tool_reference:copy(tool.reference),argument_bindings:{target:{constant:'보존할 대상'}}});}installDefinition(h,value);h.state.capabilities.can_author=false;h.state.capabilities.managed_systems=[];h.state.workflow.can_manage=false;h.render();await h.node();const before=h.draft();assert.equal(h.fields.filter(f=>f.name).every(f=>f.disabled||f.attributes.readonly!==undefined),true);assert.equal(h.buttons.some(b=>['job_menu','delete_node','move_up','move_down','save'].includes(b.dataset.authorAction)),false);h.field('job_guidance','금지된 변경');h.click('save');await flush();assert.deepEqual(h.draft(),before);assert.equal(h.writes.length,0);
});
test('A12 unrelated editing preserves all JSON types, unknown fields and opaque result links',async()=>{
 const h=harness(),schema={properties:{text:{type:'string'},zero:{type:'integer'},flag:{type:'boolean'},list:{type:'array'},object:{type:'object'},nullable:{type:'string'},prompt:{type:'string'}}},tool=c66LegacyTool(h,schema),value=definition();Object.assign(value.nodes.j,{mode:'tool',tool_contract_id:tool.id,tool_contract_revision:2,tool_reference:{...copy(tool.reference),content_hash:'older-preserved'},argument_bindings:{text:{constant:''},zero:{constant:0},flag:{constant:false},list:{constant:['x',0,false]},object:{constant:{nested:['x'],nullable:null}},nullable:{constant:null},prompt:{result:{job_id:'opaque',path:['items'],value_field:'id',confirmed:true,extension:'keep'}}},inputs:[{id:'private-input',name:'기존 입력',type:'text',scope:'factory',options_query:{extension:'keep'},opaque:{keep:true}}],condition:{all:[{field:'factory_id',op:'eq',value:'f'}]},completion:{rule:'기존 기준',opaque:'keep'},read_retry:{count:2,deadline_seconds:45},skills:['opaque-skill'],human_confirmation:false,extension:{private:'keep'}});installDefinition(h,value);await h.node();await a12Open(h);await h.modalClose('cancel');assert.deepEqual(h.draft().definition,value);h.field('job_guidance','안내만 바꿨습니다');h.click('save');await flush();const expected=copy(value);expected.nodes.j.instructions='안내만 바꿨습니다';expected.nodes.j.description='';assert.deepEqual(h.writes[0].definition,expected);
});
for(const [type,initial,raw,expected] of [['string','old','new','new'],['integer',1,'500',500],['boolean',true,'false',false],['array',['old'],'["x",0,false]',['x',0,false]],['object',{old:1},'{"nested":[0],"nullable":null}',{nested:[0],nullable:null}]])test('A12 explicit setup preserves declared JSON type through save/reload: '+type,async()=>{
 const h=harness(),tool=c66LegacyTool(h,{properties:{value:{type}}}),value=definition();Object.assign(value.nodes.j,{mode:'tool',tool_contract_id:tool.id,tool_reference:copy(tool.reference),argument_bindings:{value:{constant:initial}}});installDefinition(h,value);await h.node();await a12Open(h);h.modalField('data-job-tool-value','value',raw);await h.modalClose('apply');assert.deepEqual(h.draft().definition.nodes.j.argument_bindings.value,{constant:expected});h.click('save');await flush();assert.deepEqual(h.writes[0].definition.nodes.j.argument_bindings.value,{constant:expected});await h.open('q');await h.open('w');assert.deepEqual(h.draft().definition.nodes.j.argument_bindings.value,{constant:expected});
});
test('A12 a late setup apply cannot alter a different workflow',async()=>{const h=harness();await c66SelectShared(h);const before=copy(h.workflows.get('q').draft);await a12Open(h,'shared:managed-get_page');h.modalField('data-job-tool-value','page_id','late');await h.open('q');await h.modalClose('apply');assert.deepEqual(h.draft().definition,before);assert.equal(h.writes.length,0);});
test('A12 a late D5 confirmation cannot alter a different workflow',async()=>{const h=harness();await c66SelectShared(h);const before=copy(h.workflows.get('q').draft);h.dialogs.push({});h.dialogHook=()=>h.open('q');h.field('mode','human','change');await flush();assert.deepEqual(h.draft().definition,before);assert.equal(h.writes.length,0);});

test('A12 ordinary edits enable the existing Save button without replacing the focused control',async()=>{
 const h=harness();await h.node();const save=actionButton(h,'save'),validate=actionButton(h,'validate'),field=h.fields.find(value=>value.name==='job_guidance');
 assert.equal(save.disabled,true);assert.equal(validate.disabled,false);h.field('job_guidance','직접 편집한 작업 안내');
 assert.equal(actionButton(h,'save'),save);assert.equal(h.fields.find(value=>value.name==='job_guidance'),field);assert.equal(save.disabled,false);assert.equal(validate.disabled,true);
 h.click('save');await flush();assert.equal(h.writes[0].definition.nodes.j.instructions,'직접 편집한 작업 안내');assert.equal(h.draft().dirty,false);assert.equal(actionButton(h,'save').disabled,true);
});
for(const [type,value] of [['string','보존할 값'],[undefined,42],[undefined,{nested:[0,false]}]])test('A12 editing another answer preserves untouched constant types and binding extensions: '+(type||typeof value),async()=>{
 const h=harness(),schema={properties:{kept:type?{type}:{},changed:{type:'string'}}},tool=c66LegacyTool(h,schema),definitionValue=definition();
 Object.assign(definitionValue.nodes.j,{mode:'tool',tool_contract_id:tool.id,tool_reference:copy(tool.reference),argument_bindings:{kept:{constant:value,extension:{opaque:true}},changed:{constant:'old'}}});installDefinition(h,definitionValue);await h.node();await a12Open(h);
 h.modalField('data-job-tool-value','changed','new');assert.equal(await h.modalClose('apply'),true);assert.deepEqual(h.draft().definition.nodes.j.argument_bindings.kept,definitionValue.nodes.j.argument_bindings.kept);assert.deepEqual(h.draft().definition.nodes.j.argument_bindings.changed,{constant:'new'});
});
test('A12 an optional default can be explicitly omitted without recreating a pinned constant',async()=>{
 const h=harness();sharedReviewFixture(h);h.render();await h.node();await a12Connect(h,'managed-search_pages',{runtime:false,values:{query:'기존 검색',limit:'10'}});await a12Open(h);h.modalField('data-job-tool-value','limit','');assert.equal(await h.modalClose('apply'),true);assert.equal(h.draft().definition.nodes.j.argument_bindings.limit,undefined);h.click('save');await flush();const saved=h.draft();await a12Open(h);await h.modalClose('apply');assert.deepEqual(h.draft(),saved);
});
test('A12 invalid editing blocks apply even when the draft model still equals the original value',async()=>{
 const h=harness(),tool=c66LegacyTool(h,{properties:{value:{type:'integer'}}}),value=definition();Object.assign(value.nodes.j,{mode:'tool',tool_contract_id:tool.id,tool_reference:copy(tool.reference),argument_bindings:{value:{constant:10,extension:'keep'}}});installDefinition(h,value);await h.node();await a12Open(h);h.modalField('data-job-tool-value','value','invalid');assert.equal(await h.modalClose('apply'),false);assert.deepEqual(h.draft().definition,value);h.modalField('data-job-tool-value','value','11');assert.equal(await h.modalClose('apply'),true);assert.deepEqual(h.draft().definition.nodes.j.argument_bindings.value,{constant:11,extension:'keep'});
});
test('A12 unknown legacy automatic completion is shown as preserved and is not silently changed by inspection',async()=>{
 const h=harness(),tool=c66LegacyTool(h,{properties:{value:{type:'string'}}}),value=definition();Object.assign(value.nodes.j,{mode:'tool',tool_contract_id:tool.id,tool_reference:copy(tool.reference),argument_bindings:{value:{constant:'대상'}},human_confirmation:false,completion:{rule:'기존 확인 기준'}});installDefinition(h,value);await h.node();const auto=h.fields.find(field=>field.name==='result_confirmation'&&field.value==='automatic');assert.equal(auto.checked,true);assert.equal(auto.disabled,true);assert.match(h.markup,/기존 자동 완료 설정을 유지합니다/);assert.deepEqual(h.draft().definition,value);await a12Open(h);await h.modalClose('apply');assert.deepEqual(h.draft().definition,value);assert.equal(h.draft().dirty,false);assert.equal(h.writes.length,0);
});

function a12DefinitionField(h,kind,id,key,value,event='input',index){
 const control=h.fields.find(field=>field.dataset.definitionField===key&&(kind==='input'?field.dataset.startInputId===id:field.dataset.judgmentJobId===id&&field.dataset.judgmentIndex===String(index)));
 assert.ok(control,'definition field '+kind+' '+id+' '+key);if(control.type==='checkbox')control.checked=value;else control.value=value;control.focus();h.designer.handleEvent({type:event,target:control});return control;
}
test('A12 inline start definitions preserve object choices and metadata on no-op, and edit only the selected input',async()=>{
 const h=harness(),value=definition();value.nodes.p.inputs=[{id:'kind',name:'문서 종류',type:'single',scope:'run',options:[{id:'a',name:'설계서',extension:'keep'}],options_source:'manual',custom:{keep:true}},{id:'count',name:'개수',type:'number',scope:'run',unit:'건',required:true,default:0},{id:'private',name:'공장 설정',type:'text',scope:'workflow',custom:{keep:true}}];installDefinition(h,value);h.click('tab',{tab:'schedule'});await flush();
 a12DefinitionField(h,'input','kind','options','설계서');a12DefinitionField(h,'input','kind','required',false,'change');assert.deepEqual(h.draft().definition,value);assert.equal(h.draft().dirty,false);assert.equal(h.fields.some(field=>field.dataset.startInputId==='private'),false);
 const control=a12DefinitionField(h,'input','count','name','대상 개수');assert.equal(h.document.activeElement,control);assert.equal(h.draft().dirty,true);assert.equal(actionButton(h,'save').disabled,false);
 h.click('tab',{tab:'history'});await flush();h.click('tab',{tab:'schedule'});await flush();h.click('save');await flush();const expected=copy(value);expected.nodes.p.inputs[1].name='대상 개수';assert.deepEqual(h.writes[0].definition,expected);assert.equal(h.operations.length,0);
});
test('A12 inline judgment edits clone inherited IDs only on change and preserve unrelated guidance and references',async()=>{
 const h=harness(),value=definition();value.judgments=[{id:'old-id',label:'승인',status:'completed',consequence:'기존 안내',extension:{keep:true}}];value.nodes.j.result_block='item_verdict';value.nodes.j.suggestion_rules={rules:[{id:'rule',judgment_id:'old-id',condition:'기존 조건'}],human_only_judgment_ids:['old-id'],opaque:true};value.nodes.j.confirmation_notes='기존 확정 안내';installDefinition(h,value);h.click('tab',{tab:'rules'});await flush();
 a12DefinitionField(h,'judgment','j','label','승인','input',0);assert.deepEqual(h.draft().definition,value);assert.equal(h.draft().dirty,false);assert.match(h.markup,/기존 제안 설정/);
 a12DefinitionField(h,'judgment','j','consequence','새 후속 설명','input',0);h.click('save');await flush();const saved=h.writes[0].definition;assert.deepEqual(saved.judgments,value.judgments);assert.deepEqual(saved.nodes.j.judgments,[{...value.judgments[0],consequence:'새 후속 설명'}]);assert.deepEqual(saved.nodes.j.suggestion_rules,value.nodes.j.suggestion_rules);assert.equal(saved.nodes.j.confirmation_notes,'기존 확정 안내');
});
test('A12 policy notes preserve supported, unknown and absent policy enums through tab visits and save',async()=>{
 const h=harness(),value=definition();value.completion_policy='legacy-private';value.delivery_policy='draft_only';value.completion_notes='기존 설명';installDefinition(h,value);h.click('tab',{tab:'rules'});await flush();assert.equal(h.fields.some(field=>['completion_policy','unapproved_policy','delivery_policy'].includes(field.name)),false);assert.match(h.markup,/기존 정책 · 지원 여부 확인 필요/);assert.equal(h.forms['ew-author-rules'],undefined);assert.deepEqual(h.draft().definition,value);
 h.field('completion_notes','새 설명');h.click('tab',{tab:'history'});await flush();assert.equal(h.writes.length,0);h.click('tab',{tab:'rules'});await flush();h.click('save');await flush();const expected=copy(value);expected.completion_notes='새 설명';expected.unapproved_notes='';expected.delivery_notes='';assert.deepEqual(h.writes[0].definition,expected);assert.equal(h.operations.length,0);
});
test('A12 read-only inline definitions cannot mutate stored inputs or judgment defaults',async()=>{
 const h=harness(),value=definition();value.nodes.p.inputs=[{id:'target',name:'대상',type:'text',scope:'run'}];value.nodes.j.result_block='item_verdict';installDefinition(h,value);h.state.workflow.can_manage=false;h.state.capabilities.can_author=false;h.state.capabilities.managed_systems=[];h.render();h.click('tab',{tab:'schedule'});await flush();a12DefinitionField(h,'input','target','name','금지된 이름');h.click('tab',{tab:'rules'});await flush();a12DefinitionField(h,'judgment','j','label','금지된 판정','input',0);assert.deepEqual(h.draft().definition,value);assert.equal(h.draft().dirty,false);assert.equal(h.writes.length,0);
});
test('A12 followup tab clicks and arrow keys focus the selected tab without changing the definition',async()=>{
 const h=harness(),before=h.draft();for(const tab of ['schedule','rules','history','content']){h.click('tab',{tab});await flush();const selected=h.buttons.find(button=>button.dataset.authorAction==='tab'&&button.dataset.tab===tab);assert.equal(h.document.activeElement,selected);assert.equal(selected.getAttribute('aria-selected'),'true');}
 for(const [key,expected] of [['ArrowRight','schedule'],['End','history'],['Home','content']]){h.designer.handleEvent({type:'keydown',key,target:h.document.activeElement});await flush();assert.equal(h.document.activeElement.dataset.tab,expected);}
 assert.deepEqual(h.draft(),before);assert.equal(h.writes.length,0);assert.equal(h.operations.length,0);
});
test('A12 followup tool dialog close restores the new trigger after immediate or animated apply and cancel',async()=>{
 for(const immediate of [false,true])for(const kind of ['apply','cancel']){const h=harness();await c66SelectShared(h);const before=h.draft();await a12Open(h);h.modalField('data-job-tool-runtime','query',false,'change');h.modalField('data-job-tool-value','query','새 검색어');await h.modalClose(kind,{immediate});assert.equal(h.document.activeElement,actionButton(h,'job_tool_setup'));assert.equal(h.document.activeElement.isConnected,true);if(kind==='cancel')assert.deepEqual(h.draft(),before);else assert.deepEqual(h.draft().definition.nodes.j.argument_bindings.query,{constant:'새 검색어'});assert.equal(h.writes.length,0);}
});
test('A12 followup a closing tool dialog never steals focus or changes a newer workflow',async()=>{
 const h=harness();await c66SelectShared(h);await a12Open(h);await h.open('q');await h.node();const target=h.fields.find(field=>field.name==='job_guidance');target.focus();const before=h.draft();await h.modalClose('cancel',{immediate:true});assert.equal(h.document.activeElement,target);assert.deepEqual(h.draft(),before);assert.equal(h.writes.length,0);
});
test('A12 followup schedule tools require an explicit menu action and preserve existing collapsed schedules',async()=>{
 const h=harness(),value=definition();value.mode='periodic';value.schedule={timezone:'Asia/Seoul',frequency:'weekly',interval:2};installDefinition(h,value);h.click('tab',{tab:'schedule'});await flush();const before=h.draft();assert.equal(actionButton(h,'schedule_preview'),undefined);assert.equal(actionButton(h,'schedule_create'),undefined);assert.ok(actionButton(h,'schedule_tools'));
 h.click('schedule_tools');await flush();assert.ok(actionButton(h,'schedule_preview'));assert.ok(actionButton(h,'schedule_create'));assert.equal(h.details.find(item=>item.className==='ew-author-schedules').open,true);assert.equal(h.document.activeElement,h.host.querySelector('.ew-author-schedules>summary'));assert.deepEqual(h.draft(),before);assert.equal(h.operations.length,0);
 const other=harness();installDefinition(other,value);other.state.operations={schedules:[{id:'stored',workflow_id:'w',version:3,identity_user_id:'a',enabled:true,delegated:false,rule:{timezone:'Asia/Seoul',frequency:'weekly'}}]};other.render();other.click('tab',{tab:'schedule'});await flush();assert.equal(other.details.find(item=>item.className==='ew-author-schedules').open,false);assert.match(other.markup,/게시 v3/);assert.equal(other.writes.length,0);assert.equal(other.operations.length,0);
});
test('A12 followup inline purpose remains private until an explicit draft save and never gains factory ownership',async()=>{
 const h=harness();h.selection.factory_id='f';await beginCreation(h,'설계한 업무','직접 적은 목적');const button=actionButton(h,'procedure_create'),field=h.fields.find(item=>item.id==='ew-procedure-description');h.field('ew-procedure-description','최종 목적','change');assert.equal(actionButton(h,'procedure_create'),button);assert.equal(h.fields.find(item=>item.id==='ew-procedure-description'),field);await submitCreation(h);
 assert.equal(h.writes.length,1);assert.equal(h.writes[0].description,undefined);assert.equal(h.writes[0].factory_id,undefined);assert.equal(h.workflows.get('created-1').draft.description,undefined);assert.equal(h.draft().definition.description,'최종 목적');assert.equal(h.draft().dirty,true);assert.equal(h.draft().definition.factory_id,undefined);
 h.click('save');await flush();assert.equal(h.writes[1].action,'save_draft');assert.equal(h.writes[1].definition.description,'최종 목적');assert.equal(h.draft().dirty,false);assert.equal(h.operations.length,0);
});
test('A12 followup opening another workflow protects the unfinished creation buffer and the old private draft',async()=>{
 const h=harness();await h.node();h.field('job_guidance','기존 미저장 안내');const before=h.draft().definition;await beginCreation(h,'새 워크플로우','새 목적');h.click('open',{id:'q'});await flush();assert.equal(h.selection.workflow_id,'');assert.ok(h.forms['ew-procedure-create']);assert.match(h.markup,/추가하거나 취소한 뒤/);assert.equal(h.fields.find(field=>field.id==='ew-procedure-description').value,'새 목적');assert.equal(h.writes.length,0);
 h.click('procedure_cancel');await flush();h.click('open',{id:'w'});await flush();assert.deepEqual(h.draft().definition,before);assert.equal(h.draft().dirty,true);assert.equal(h.writes.length,0);
});

test('A12 generated prompts: new shared constants do not create unused required runtime questions',async()=>{
 for(const [id,argument,value] of [['managed-get_page','page_id','123'],['managed-search_pages','query','설치 가이드']]){
  const h=harness();sharedReviewFixture(h);h.render();await h.node();await a12Connect(h,id,{runtime:false,values:{[argument]:value}});
  const node=h.draft().definition.nodes.j;assert.deepEqual(node.argument_bindings[argument],{constant:value});assert.deepEqual(node.inputs,[],'constant-only new connection cannot leave generated run questions');
  const before=h.draft();await a12Open(h);assert.equal(h.modal.querySelector('[data-job-tool-runtime="'+argument+'"]').checked,false);await h.modalClose('apply');assert.deepEqual(h.draft(),before);assert.equal(h.operations.length,0);
 }
});
test('A12 generated prompts: asking at runtime retains only the explicitly used generated question',async()=>{
 const h=harness();sharedReviewFixture(h);h.render();await h.node();h.field('mode','tool','change');await flush();await a12Open(h,'shared:managed-search_pages');
 h.modalField('data-job-tool-runtime','query',true,'change');await h.modalClose('apply');const node=h.draft().definition.nodes.j;
 assert.deepEqual(node.argument_bindings.query,{input:'query'});assert.deepEqual(node.inputs.map(field=>field.id),['query']);assert.equal(node.inputs[0].required,true);assert.equal(node.inputs[0].scope,'run');assert.equal(h.writes.length,0);
});
test('A12 generated prompts: pre-existing same-name and opaque legacy inputs survive a new constant connection',async()=>{
 const h=harness();sharedReviewFixture(h);const value=definition(),inputs=[{id:'page_id',name:'직접 만든 입력',type:'text',scope:'workflow',required:true,extension:{keep:true}},{id:'legacy-note',name:'기존 입력',type:'text',scope:'run',source:{opaque:'keep'}}];value.nodes.j.inputs=copy(inputs);installDefinition(h,value);await h.node();
 await a12Connect(h,'managed-get_page',{runtime:false,values:{page_id:'123'}});const node=h.draft().definition.nodes.j;assert.deepEqual(node.inputs,inputs);assert.deepEqual(node.argument_bindings.page_id,{constant:'123'});h.click('save');await flush();assert.deepEqual(h.writes[0].definition.nodes.j.inputs,inputs);
});
test('A12 generated prompts: same-tool edits and cancellation never clean up existing input definitions',async()=>{
 const h=harness(),{read}=sharedReviewFixture(h),value=definition();Object.assign(value.nodes.j,{mode:'tool',shared_tool_id:read.id,inputs:[{id:'page_id',name:'기존 도구 입력',type:'text',required:true,scope:'run',source:{shared_tool_id:read.id},extension:'keep'}],argument_bindings:{page_id:{constant:'123'}},human_confirmation:false});installDefinition(h,value);await h.node();
 await a12Open(h);h.modalField('data-job-tool-value','page_id','456');await h.modalClose('cancel');assert.deepEqual(h.draft().definition,value);
 await a12Open(h);h.modalField('data-job-tool-value','page_id','456');await h.modalClose('apply');const expected=copy(value);expected.nodes.j.argument_bindings.page_id.constant='456';assert.deepEqual(h.draft().definition,expected);assert.equal(h.writes.length,0);
});
test('A12 generated prompts: a temporary runtime choice returns to a constant without dirtying the original',async()=>{
 const h=harness(),{read}=sharedReviewFixture(h),value=definition();Object.assign(value.nodes.j,{mode:'tool',shared_tool_id:read.id,inputs:[],argument_bindings:{page_id:{constant:'123'}},human_confirmation:false});installDefinition(h,value);await h.node();const before=h.draft();
 await a12Open(h);h.modalField('data-job-tool-runtime','page_id',true,'change');h.modalField('data-job-tool-runtime','page_id',false,'change');await h.modalClose('apply');assert.deepEqual(h.draft(),before);assert.equal(h.writes.length,0);
});
test('A12 generated prompts: legacy execution bindings keep a newly generated input that they still reference',async()=>{
 const h=harness();sharedReviewFixture(h);const value=definition();value.nodes.j.argument_bindings={};value.nodes.j.execution={argument_bindings:{legacy_argument:{input:'page_id',extension:'keep'}}};installDefinition(h,value);await h.node();await a12Connect(h,'managed-get_page',{runtime:false,values:{page_id:'123'}});
 const node=h.draft().definition.nodes.j;assert.deepEqual(node.execution,value.nodes.j.execution);assert.deepEqual(node.inputs.map(input=>input.id),['page_id']);assert.deepEqual(node.argument_bindings.page_id,{constant:'123'});
});
