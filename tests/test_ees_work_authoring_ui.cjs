/* Production authoring state/form contracts with a small synthetic DOM.
 * These checks are not actual Native browser acceptance tests. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const crypto = require('node:crypto');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../branding/ees/ui/ees-work-designer.js'), 'utf8');
const copy = value => JSON.parse(JSON.stringify(value));
const flush = async () => { for (let i=0;i<5;i++) await new Promise(resolve=>setImmediate(resolve)); };
const deferred = () => { let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject}; };
const decode = value => String(value).replaceAll('&quot;','"').replaceAll('&#39;',"'").replaceAll('&lt;','<').replaceAll('&gt;','>').replaceAll('&amp;','&');
const attr = (text,name) => decode(text.match(new RegExp('(?:^|\\s)'+name+'="([^"]*)"'))?.[1] || '');
function parseForm(html,dataset={}) {
  const controls=[];
  for(const match of html.matchAll(/<input\b([^>]*)>/g)) {const a=match[1];controls.push({name:attr(a,'name'),id:attr(a,'id'),value:attr(a,'value')||'on',type:attr(a,'type'),checked:/\bchecked\b/.test(a),disabled:/\bdisabled\b/.test(a)});}
  for(const match of html.matchAll(/<textarea\b([^>]*)>([\s\S]*?)<\/textarea>/g)) controls.push({name:attr(match[1],'name'),id:attr(match[1],'id'),value:decode(match[2]),type:'textarea',disabled:/\bdisabled\b/.test(match[1])});
  for(const match of html.matchAll(/<select\b([^>]*)>([\s\S]*?)<\/select>/g)) {
    const options=[...match[2].matchAll(/<option\b([^>]*)>([^<]*)<\/option>/g)],selected=options.find(item=>/\bselected\b/.test(item[1]))||options[0];
    controls.push({name:attr(match[1],'name'),id:attr(match[1],'id'),value:selected?(attr(selected[1],'value')||decode(selected[2])):'',type:'select',disabled:/\bdisabled\b/.test(match[1])});
  }
  return {controls,dataset,querySelector(selector){const name=selector.match(/name=["']?([^"'\]]+)/)?.[1];return controls.find(item=>item.name===name)||null;},querySelectorAll(){return controls;}};
}
function workflow(id,system='EMS') {
  const node=(id,type,parent,children)=>({id,type,parent,children,category:'setup',name:id,description:'목적',instructions:'원래 안내',rule:'담당자 확인',condition:'all',enabled:true,mode:'manual',tools:[],skills:[],bindings:{},deps:[],systems:[system]});
  return {process_id:id,nodes:{[id]:node(id,'p',null,[id+'-t']),[id+'-t']:node(id+'-t','t',id,[id+'-j']),[id+'-j']:node(id+'-j','j',id+'-t',[])},tools:{},skills:{}};
}
function harness() {
  const h={markup:'',writes:[],reads:[],dialogs:[],replies:[],cap:{ok:true,actor_id:'user-a',is_admin:false,managed_systems:['EMS','FDC'],can_author:true},denied:false};
  h.references={tools:{shared:{id:'shared',name:'공유 도구',input:'site',adapter:'unavailable',source:'open_webui',reference:'native-shared'}},skills:{common:{id:'common',name:'공통 스킬',locked:true}},sites:{s:{id:'s',name:'공장',country:'한국'}},systems:['EMS','FDC'],available_tools:[{id:'native-tool',name:'Native 도구'}],available_skills:[{id:'native-skill',name:'Native 스킬'}],assets_available:true};
  h.processes=new Map(['p','q','m'].map(id=>{const owner_system=id==='m'?'FDC':'EMS';return [id,{process_id:id,name:id,owner_system,owner_revision:1,draft_revision:1,published_version:1,enabled:true,workflow:workflow(id,owner_system),validated_revision:1}];}));
  h.envelope=(system='EMS',process='')=>({ok:true,actor_id:h.cap.actor_id,capabilities:copy(h.cap),system_id:system,processes:[...h.processes.values()].filter(p=>p.owner_system===system).map(({workflow,...p})=>p),process:process?copy(h.processes.get(process)):null,references:copy(h.references)});
  let form=null,assets=[],dialog=null;h.mutations=[];const status={textContent:''};
  const noop=()=>{};
  const section={dataset:{},style:{},classList:{add:noop,remove:noop},isConnected:true,contains:()=>false,remove(){this.isConnected=false;},querySelectorAll(selector){if(selector==='.ew-asset-form')return assets;if(selector==='button[data-mutation]')return h.mutations;if(selector==='input,textarea,select')return [...(form?.controls||[]),...assets.flatMap(f=>f.controls)];return [];},set innerHTML(html){h.markup=html;h.mutations=[...html.matchAll(/<button\b([^>]*data-mutation[^>]*)>/g)].map(match=>({dataset:{action:attr(match[1],'data-action')},disabled:/\bdisabled\b/.test(match[1])}));const node=html.match(/<form id="ees-work-node-form"[^>]*>([\s\S]*?)<\/form>/);form=node?parseForm(node[1]):null;assets=[...html.matchAll(/<form class="ew-card ew-asset-form"([^>]*)>([\s\S]*?)<\/form>/g)].map(m=>parseForm(m[2],{kind:attr(m[1],'data-kind'),assetId:attr(m[1],'data-asset-id')}));},get innerHTML(){return h.markup;}};
  const chat={hidden:false,classList:{add:noop,remove:noop}};
  const container={children:[chat],parentElement:{querySelector:()=>null},append(element){element.parentElement=this;element.isConnected=true;}};chat.parentElement=container;
  const query=selector=>selector==='#chat-container'?chat:selector==='#ees-work-node-form'?form:selector==='#ees-work-designer .ew-designer-status'?status:selector==='#ees-work-dialog'?dialog:null;
  const callbacks={authoringRead:async route=>{h.reads.push(route);if(h.readOverride){const value=h.readOverride(route);if(value!==undefined)return await value;}if(route==='authoring/capabilities')return copy(h.cap);const url=new URL('http://local/'+route),system=url.searchParams.get('system_id')||'EMS',process=url.searchParams.get('process_id')||'';if(process&&h.denied)throw Object.assign(new Error('선택 P 접근 불가'),{status:404,code:'process_not_found'});return h.envelope(system,process);},authoringWrite:async body=>{h.writes.push(copy(body));if(h.writeOverride)return await h.writeOverride(body);const item=h.processes.get(body.process_id);if(body.action==='save_draft'){item.workflow=copy(body.payload.workflow);item.draft_revision++;item.validated_revision=null;}if(body.action==='validate_draft')item.validated_revision=item.draft_revision;return h.envelope(body.system_id,body.process_id);},authoringModels:async()=>{h.modelReads=(h.modelReads||0)+1;return h.modelsOverride?await h.modelsOverride():{models:[{id:'model-a',name:'모델'}],preferred:['model-a']};},authoringReply:async value=>{h.replies.push(value);return h.replyOverride?await h.replyOverride(value):JSON.stringify({answer:'수정했습니다',instructions:'AI 새 안내'});}};
  const workUI={$:query,esc:value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;'),clone:copy,categories:{setup:'설치',ops:'운영',incident:'장애'},levels:{p:'P',t:'T',j:'J'},button:(label,action,extra='')=>`<button data-action="${action}" ${extra}>${label}</button>`,treeHTML:()=>'',lineage(id,data){const result=[];for(let n=data.nodes[id];n;n=data.nodes[n.parent])result.unshift(n);return result;},dialog:({title,html})=>{h.dialogHistory=(h.dialogHistory||[]).concat({title,html});const answer=h.dialogs.shift();assert.notEqual(answer,undefined,'A dialog answer must be explicit in this harness');const controls=Object.entries(answer||{}).map(([name,value])=>({name,value,type:name==='choice'?'radio':'text',checked:true}));let capture;dialog={querySelectorAll:()=>controls,addEventListener:(name,cb)=>capture=cb};return Promise.resolve().then(async()=>{await h.dialogHook?.();capture?.({target:{closest:()=>true}});return answer!==null;});}};
  const context={getComputedStyle:()=>({maxWidth:h.nativeMaxWidth||'calc(100% - 244px)'}),workUI,crypto,URLSearchParams,AbortController,console,confirm:()=>true,location:{pathname:'/',search:'?ees=workflow'},document:{createElement:()=>section,querySelector:query,activeElement:null},FormData:class {constructor(f){this.values=new Map();for(const field of f.controls)if(field.name&&!field.disabled&&(!['checkbox','radio'].includes(field.type)||field.checked)){this.values.set(field.name,[...(this.values.get(field.name)||[]),field.value]);}}has(key){return this.values.has(key);}get(key){return this.values.get(key)?.[0]??null;}getAll(key){return this.values.get(key)||[];}}};
  vm.createContext(context);vm.runInContext(source,context);context.callbacks=callbacks;h.designer=vm.runInContext('createWorkDesigner({callbacks})',context);
  h.designer.render({adminRoute:true});
  h.click=(action,dataset={})=>h.designer.handleEvent({type:'click',target:{closest:selector=>selector==='#ees-work-designer'?section:{dataset:{action,...dataset}}}});
  h.control=(id,value,type='change')=>h.designer.handleEvent({type,target:{id,value,closest:selector=>selector==='#ees-work-designer'?section:null}});
  h.change=(name,value)=>{const field=form?.querySelector('[name="'+name+'"]');assert.ok(field,name+' form control');field.value=value;h.control('',value,'input');};
  h.checkbox=(name,checked)=>{const field=form.querySelector('[name="'+name+'"]');assert.ok(field);field.checked=checked;h.control('',checked,'input');};
  h.asset=(kind,reference)=>{h.click('editor_tab',{tab:kind});h.click('add_asset',{kind});const field=assets.at(-1).querySelector('[name="reference"]');field.value=reference;h.control('',reference,'input');};
  h.open=async id=>{h.control('ees-work-manage-process',id);await flush();};
  h.init=async()=>{await h.designer.refreshAuthoring();await h.open('p');return h;};
  h.draft=()=>copy(h.designer.readDraft());h.chat=chat;h.section=section;
  return h;
}

test('runtime edit resolves the saved process owner without claiming its applicable system',async()=>{
  const h=await harness().init();h.change('instructions','이전 담당 초안 보존');
  h.cap.is_admin=true;h.cap.managed_systems=['EMS','FDC','UNASSIGNED'];
  const process={process_id:'shared-p',name:'공유 절차',owner_system:'UNASSIGNED',owner_revision:1,draft_revision:1,published_version:1,enabled:true,workflow:workflow('shared-p'),validated_revision:1};
  h.processes.set(process.process_id,process);
  h.readOverride=route=>{if(route==='authoring/capabilities')return;const query=new URL('http://local/'+route).searchParams;if(query.get('process_id')!==process.process_id)return;assert.equal(query.get('system_id'),'');return h.envelope('UNASSIGNED',process.process_id);};
  assert.equal(await h.designer.openProcess(process.process_id),true);
  assert.ok(h.draft().definition.nodes[process.process_id]);assert.match(h.markup,/관리: UNASSIGNED/);assert.equal(h.writes.length,0);
  await h.designer.openProcess('p');assert.equal(h.draft().definition.nodes.p.instructions,'이전 담당 초안 보존');
});
test('runtime edit denial cannot expose a draft or perform authoring writes',async()=>{
  const h=await harness().init();h.change('instructions','회수 전 초안');h.denied=true;
  assert.equal(await h.designer.openProcess('q'),false);assert.equal(h.designer.canAuthor(),false);
  assert.equal(h.draft().definition.nodes.p.instructions,'회수 전 초안');assert.equal(h.draft().definition.nodes.q,undefined);assert.equal(h.writes.length,0);
  h.cap.can_author=false;const count=h.reads.length;assert.equal(await h.designer.openProcess('q'),false);
  assert.deepEqual(h.reads.slice(count),['authoring/capabilities']);
});
test('dirty P/system navigation keeps, saves, or discards only the selected P',async()=>{
  const h=await harness().init();h.change('instructions','P 보존할 글');h.dialogs.push({choice:'keep'});await h.open('q');assert.equal(h.draft().definition.nodes.q.instructions,'원래 안내');await h.open('p');assert.equal(h.draft().definition.nodes.p.instructions,'P 보존할 글');
  h.dialogs.push({choice:'save'});await h.open('q');assert.equal(h.writes.length,1);assert.equal(h.writes[0].process_id,'p');assert.equal(h.writes[0].payload.workflow.nodes.p.instructions,'P 보존할 글');
  h.change('instructions','Q 버릴 글');h.dialogs.push({choice:'discard'});h.control('ees-work-manage-system','FDC');await flush();await h.open('m');h.control('ees-work-manage-system','EMS');await flush();await h.open('q');assert.equal(h.draft().definition.nodes.q.instructions,'원래 안내');
});
test('cancelling dirty navigation preserves the selected P and text',async()=>{const h=await harness().init();h.change('instructions','남긴 글');h.dialogs.push(null);await h.open('q');assert.equal(h.draft().definition.nodes.p.instructions,'남긴 글');assert.equal(h.writes.length,0);});
test('404 revocation makes draft read-only, preserves text, and blocks save and AI undo',async()=>{
  const h=await harness().init();h.control('ees-work-authoring-input','안내 수정','input');h.click('ai_edit');await flush();assert.equal(h.draft().definition.nodes.p.instructions,'AI 새 안내');h.denied=true;await h.designer.refreshAuthoring();assert.equal(h.designer.canAuthor(),false);h.click('ai_undo');h.click('save_draft');await flush();assert.equal(h.writes.length,0);assert.equal(h.draft().definition.nodes.p.instructions,'AI 새 안내');assert.match(h.markup,/현재 세션에 보존/);
});
test('404 save rejection preserves current text and immediately locks authoring',async()=>{const h=await harness().init();h.change('instructions','회수 직전 글');h.writeOverride=async()=>{throw Object.assign(new Error('P unavailable'),{status:404});};h.click('save_draft');await flush();assert.equal(h.designer.canAuthor(),false);assert.equal(h.draft().definition.nodes.p.instructions,'회수 직전 글');});
test('fresh selected P permission is checked before sending AI context',async()=>{const h=await harness().init();h.control('ees-work-authoring-input','이 글 수정','input');h.denied=true;h.click('ai_edit');await flush();assert.equal(h.replies.length,0);assert.equal(h.designer.canAuthor(),false);assert.match(h.markup,/이 글 수정/);});
test('owner revision change before AI blocks sending even when global authorship remains',async()=>{const h=await harness().init();h.processes.get('p').owner_revision++;h.control('ees-work-authoring-input','바꿔 줘','input');h.click('ai_edit');await flush();assert.equal(h.replies.length,0);assert.equal(h.designer.canAuthor(),false);});
test('late AI response cannot update another P and conversations stay P scoped',async()=>{const h=await harness().init(),pending=deferred();h.replyOverride=()=>pending.promise;h.control('ees-work-authoring-input','P 질문','input');h.click('ai_edit');await flush();await h.open('q');pending.resolve(JSON.stringify({answer:'late',instructions:'잘못된 응답'}));await flush();assert.equal(h.draft().definition.nodes.q.instructions,'원래 안내');assert.doesNotMatch(h.markup,/P 질문|잘못된 응답/);await h.open('p');assert.equal(h.draft().definition.nodes.p.instructions,'원래 안내');assert.match(h.markup,/P 질문/);});
test('late read is ignored after a newer P selection',async()=>{const h=await harness().init(),pending=deferred();h.readOverride=route=>route.includes('process_id=q')?pending.promise:undefined;h.control('ees-work-manage-process','q');await flush();await h.open('p');pending.resolve(h.envelope('EMS','q'));await flush();assert.ok(h.draft().definition.nodes.p);assert.equal(h.draft().definition.nodes.q,undefined);});
test('late save cannot restore data after account reset',async()=>{const h=await harness().init(),pending=deferred();h.change('instructions','사용자 A 비공개 글');h.writeOverride=()=>pending.promise;h.click('save_draft');await flush();h.designer.reset();h.cap.actor_id='user-b';h.designer.render({adminRoute:true});await h.designer.refreshAuthoring();await h.open('q');pending.resolve(h.envelope('EMS','p'));await flush();assert.ok(h.draft().definition.nodes.q);assert.doesNotMatch(h.markup,/사용자 A 비공개 글/);});
test('continuing to type during save retains newer text and advances only acknowledged revision',async()=>{const h=await harness().init(),pending=deferred();h.change('instructions','저장한 글');h.writeOverride=()=>pending.promise;h.click('save_draft');await flush();h.change('instructions','요청 뒤 새 글');const response=h.envelope('EMS','p');response.process.workflow=h.writes[0].payload.workflow;response.process.draft_revision=2;pending.resolve(response);await flush();assert.equal(h.draft().definition.nodes.p.instructions,'요청 뒤 새 글');assert.equal(h.draft().revision,2);assert.equal(h.draft().dirty,true);});
test('Native Tool and Skill connections send only the scoped metadata contract',async()=>{const h=await harness().init();h.asset('tools','native-tool');h.asset('skills','native-skill');h.click('save_draft');await flush();const payload=h.writes[0].payload.workflow,tool=Object.values(payload.tools)[0],skill=Object.values(payload.skills)[0];assert.deepEqual(Object.keys(tool).sort(),['adapter','enabled','id','input','name','reference','source']);assert.deepEqual(Object.keys(skill).sort(),['body','id','name','reference','source','type']);assert.equal(tool.reference,'native-tool');assert.equal(skill.reference,'native-skill');assert.equal(skill.body,'');assert.equal(payload.tools.shared,undefined);assert.equal(payload.skills.common,undefined);});
test('ACL-filtered shared metadata is not reclassified as P local, while opaque bindings survive',async()=>{const h=await harness().init();h.processes.get('p').workflow.nodes.p.tools=['shared'];h.processes.get('p').workflow.nodes.p.bindings={shared:'site'};await h.designer.refreshAuthoring();h.change('instructions','ACL 변경 중 글');h.references.tools={};await h.designer.refreshAuthoring();h.click('save_draft');await flush();const payload=h.writes[0].payload.workflow;assert.deepEqual(payload.tools,{});assert.deepEqual(payload.nodes.p.tools,['shared']);assert.deepEqual(payload.nodes.p.bindings,{shared:'site'});assert.equal(payload.nodes.p.instructions,'ACL 변경 중 글');assert.doesNotMatch(h.markup,/공유 도구/);});
test('canonical authoring hides and restores Native chat without changing its content',async()=>{const h=await harness().init();assert.equal(h.chat.hidden,true);h.designer.render({adminRoute:false});assert.equal(h.chat.hidden,false);});
test('account identity change clears cached drafts and late AI responses',async()=>{const h=await harness().init(),pending=deferred();h.replyOverride=()=>pending.promise;h.control('ees-work-authoring-input','계정 A 질문','input');h.click('ai_edit');await flush();h.cap.actor_id='user-b';await h.designer.refreshAuthoring();pending.resolve(JSON.stringify({answer:'A 응답',instructions:'A 글'}));await flush();assert.equal(h.draft().definition,null);h.designer.render({adminRoute:true});await h.designer.refreshAuthoring();await h.open('p');assert.doesNotMatch(h.markup,/계정 A 질문|A 응답|A 글/);});
test('launcher API discards late success and failure after token, generation, or route change',async()=>{
  const launcher=fs.readFileSync(path.join(__dirname,'../branding/ees/ui/ees-work-launcher.js'),'utf8');
  const fn=launcher.slice(launcher.indexOf('async function authoringAPI('),launcher.indexOf('\n  async function ',launcher.indexOf('async function authoringAPI(')+1));
  for(const field of ['auth','generation','route'])for(const reject of [false,true]){
    const pending=deferred(),scope={auth:'token-a',generation:1,location:{pathname:'/',search:'?ees=workflow'},token:()=>scope.auth,available:()=>true,api:()=>pending.promise};vm.createContext(scope);vm.runInContext(fn,scope);const result=scope.authoringAPI('authoring');
    if(field==='auth')scope.auth='token-b';else if(field==='generation')scope.generation++;else scope.location.search='';
    if(reject)pending.reject(new Error('old failure'));else pending.resolve({actor_id:'old user'});assert.equal(await result,null);
  }
});
test('late model listing does not leave the next P permanently loading',async()=>{const h=harness(),pending=deferred();h.modelsOverride=()=>h.modelReads===1?pending.promise:Promise.resolve({models:[{id:'model-b'}],preferred:['model-b']});await h.init();await h.open('q');pending.resolve({models:[{id:'old-model'}],preferred:['old-model']});await flush();assert.equal(h.modelReads,2);assert.match(h.markup,/model-b/);assert.doesNotMatch(h.markup,/old-model/);});
test('closed settings preserve opaque references and bindings through node selection',async()=>{const h=harness();const job=h.processes.get('p').workflow.nodes['p-j'];job.tools=['missing-tool'];job.skills=['common','missing-skill'];job.bindings={'missing-tool':'private-target'};job.systems=['EMS','legacy-system'];await h.init();h.click('edit_node',{nodeId:'p-j'});h.change('instructions','설정 보존');h.click('edit_node',{nodeId:'p-t'});h.click('edit_node',{nodeId:'p-j'});const result=h.draft().definition.nodes['p-j'];assert.deepEqual(result.tools,job.tools);assert.deepEqual(result.skills,job.skills);assert.deepEqual(result.bindings,job.bindings);assert.deepEqual(result.systems,job.systems);assert.equal(result.instructions,'설정 보존');h.checkbox('enabled',false);await h.designer.refreshAuthoring();assert.equal(h.draft().definition.nodes['p-j'].enabled,false);});
test('stage and job creation, ordering and removal retain unrelated nodes',async()=>{const h=await harness().init();h.click('add_child');let draft=h.draft().definition;const stage=draft.nodes.p.children.at(-1);assert.match(stage,/^new-/);h.change('name','새 담당 단계');h.click('add_child');draft=h.draft().definition;const job=draft.nodes[stage].children[0];assert.equal(draft.nodes[job].type,'j');h.click('edit_node',{nodeId:stage});h.click('move_up');assert.equal(h.draft().definition.nodes.p.children[0],stage);h.click('delete_node');draft=h.draft().definition;assert.equal(draft.nodes[stage],undefined);assert.equal(draft.nodes[job],undefined);assert.deepEqual(draft.nodes.p.children,['p-t']);assert.ok(draft.nodes['p-j']);});
test('large child search, filter and pagination retain unsaved parent text',async()=>{const h=harness(),flow=h.processes.get('p').workflow;for(let i=0;i<44;i++){const id='bulk-'+i;flow.nodes[id]={...copy(flow.nodes['p-j']),id,name:'검사 '+String(i).padStart(2,'0'),mode:i%2?'manual':'tool'};flow.nodes['p-t'].children.push(id);}await h.init();h.click('edit_node',{nodeId:'p-t'});assert.match(h.markup,/전체 45개 · 검색 결과 45개/);assert.equal((h.markup.match(/class="ew-editor-child"/g)||[]).length,20);h.change('instructions','검색 중 글');h.click('child_page',{page:'2'});assert.match(h.markup,/41–45 표시/);h.control('ees-work-child-search','검사 0','input');h.control('ees-work-child-mode','tool');assert.match(h.markup,/검색 결과 5개/);h.click('edit_node',{nodeId:'bulk-0'});h.click('edit_node',{nodeId:'p-t'});assert.match(h.markup,/검색 결과 5개/);assert.equal(h.draft().definition.nodes['p-t'].instructions,'검색 중 글');});
test('publish relocks on typing and requires a checked saved P revision',async()=>{const h=await harness().init(),publish=()=>h.mutations.find(button=>button.dataset.action==='publish');assert.equal(publish().disabled,false);h.change('instructions','게시 전 수정');assert.equal(publish().disabled,true);h.click('validate_draft');await flush();assert.equal(h.writes.length,0);h.click('save_draft');await flush();assert.equal(publish().disabled,true);h.click('validate_draft');await flush();assert.equal(publish().disabled,false);h.dialogs.push({});h.click('publish');await flush();assert.equal(h.writes.at(-1).action,'publish');assert.equal(h.writes.at(-1).process_id,'p');assert.equal(h.writes.at(-1).expected_draft_revision,2);});
test('only enabled built-in mock adapters are represented as executable simulations',async()=>{const h=harness(),job=h.processes.get('p').workflow.nodes['p-j'];for(const [id,settings] of Object.entries({simulated:{adapter:'mock'},missing:{},disabled:{adapter:'mock',enabled:false},native:{adapter:'mock',source:'open_webui'}})){h.references.tools[id]={id,name:id,input:'site',...settings};job.tools.push(id);job.bindings[id]='site';}await h.init();h.click('edit_node',{nodeId:'p-j'});assert.equal((h.markup.match(/합성 시연 점검/g)||[]).length,1);assert.equal((h.markup.match(/<small class="ew-muted">실행 연결 필요<\/small>/g)||[]).length,3);});
test('canonical authoring follows the Native sidebar width constraint as it opens and closes',async()=>{const h=await harness().init();assert.equal(h.section.style.maxWidth,'calc(100% - 244px)');h.nativeMaxWidth='100%';h.designer.sync({adminRoute:true});assert.equal(h.section.style.maxWidth,'100%');h.nativeMaxWidth='calc(100% - 300px)';h.designer.sync({adminRoute:true});assert.equal(h.section.style.maxWidth,'calc(100% - 300px)');});
test('switching nodes and returning before AI completes explains why its edit was not applied',async()=>{const h=await harness().init(),pending=deferred();h.replyOverride=()=>pending.promise;h.control('ees-work-authoring-input','선택한 안내 수정','input');h.click('ai_edit');await flush();h.click('edit_node',{nodeId:'p-j'});h.click('edit_node',{nodeId:'p'});pending.resolve(JSON.stringify({answer:'지연 응답',instructions:'적용하면 안 되는 글'}));await flush();assert.equal(h.draft().definition.nodes.p.instructions,'원래 안내');assert.match(h.markup,/적용하지 않았습니다/);});
test('manual editing and P save remain available without a model or when model listing fails',async()=>{for(const failure of [false,true]){const h=harness();h.modelsOverride=async()=>{if(failure)throw new Error('model list unavailable');return {models:[],preferred:[]};};await h.init();assert.equal(h.designer.canAuthor(),true);assert.match(h.markup,failure?/모델 목록을 읽지 못했습니다/:/사용할 수 있는 모델이 없습니다/);h.change('instructions','모델 없이 직접 작성');h.click('save_draft');await flush();assert.equal(h.writes.length,1);assert.equal(h.writes[0].payload.workflow.nodes.p.instructions,'모델 없이 직접 작성');assert.equal(h.replies.length,0);}});
async function reconciliationHarness(state='changed',admin=true){
  const h=harness(),item=h.processes.get('p');h.cap.is_admin=admin;
  item.published_workflow=state==='removed'?null:copy(item.workflow);
  if(item.published_workflow)item.published_workflow.nodes.p.instructions='Restore 뒤 현재 게시 안내';
  item.publication_reconciliation={required:true,current_published_fingerprint:state==='removed'?'':'a'.repeat(64),state,catalog_version:7,can_reconcile:admin};item.validated_revision=null;
  h.writeOverride=async body=>{assert.equal(body.action,'reconcile_publication');item.draft_revision++;item.validated_revision=null;item.publication_reconciliation={...item.publication_reconciliation,required:false,can_reconcile:false};return h.envelope('EMS','p');};
  await h.init();return h;
}
test('admin explicitly adopts changed or removed publication without replacing or publishing the draft',async()=>{
  for(const state of ['changed','removed']){
    const h=await reconciliationHarness(state),before=h.draft().definition,expected=state==='removed'?'':'a'.repeat(64);
    assert.equal(h.writes.length,0,'Reading a changed publication cannot adopt it');h.dialogs.push({action:'reconcile_publication'});h.click('process_actions');await flush();
    const dialog=h.dialogHistory.at(-1).html;assert.match(dialog,/현재 게시본 기준으로 다시 확인/);assert.match(dialog,/자동으로 게시하지 않습니다/);assert.match(dialog,/게시 전 확인을 다시 해야/);
    if(state==='removed'){assert.match(dialog,/현재 게시본 없음/);assert.doesNotMatch(dialog,/<option value="delete">/);}
    assert.equal(h.writes.length,1);assert.equal(h.writes[0].action,'reconcile_publication');assert.equal(h.writes[0].expected_draft_revision,1);assert.equal(h.writes[0].expected_owner_revision,1);assert.equal(h.writes[0].payload.expected_published_fingerprint,expected);assert.equal(h.writes[0].payload.workflow,undefined);
    assert.deepEqual(h.draft().definition,before);assert.equal(h.draft().revision,2);assert.equal(h.draft().dirty,false);assert.equal(h.mutations.find(button=>button.dataset.action==='publish').disabled,true);if(state==='removed')assert.match(h.markup,/현재 게시본 없음 · 마지막 게시 v1/);
  }
});
test('publication reconciliation rejects dirty inputs, non-admin choice and cancellation without losing text',async()=>{
  const dirty=await reconciliationHarness();dirty.change('instructions','현재 저장하지 않은 글');dirty.dialogs.push({action:'reconcile_publication'});dirty.click('process_actions');await flush();assert.equal(dirty.writes.length,0);assert.equal(dirty.draft().definition.nodes.p.instructions,'현재 저장하지 않은 글');assert.match(dirty.markup,/변경한 초안을 먼저 저장/);
  const reader=await reconciliationHarness('changed',false);reader.dialogs.push({action:'reconcile_publication'});reader.click('process_actions');await flush();assert.equal(reader.writes.length,0);assert.doesNotMatch(reader.dialogHistory.at(-1).html,/<option value="reconcile_publication">/);assert.match(reader.markup,/관리자에게/);
  const cancelled=await reconciliationHarness();cancelled.dialogs.push(null);cancelled.click('process_actions');await flush();assert.equal(cancelled.writes.length,0);assert.equal(cancelled.draft().revision,1);
});
test('publication reconciliation sends the exact compared revision and fingerprint after a dialog-time refresh',async()=>{
  const h=await reconciliationHarness();h.dialogHook=async()=>{h.dialogHook=null;const item=h.processes.get('p');item.draft_revision=2;item.publication_reconciliation.current_published_fingerprint='b'.repeat(64);await h.designer.refreshAuthoring();};
  h.writeOverride=async body=>{assert.equal(body.expected_draft_revision,1);assert.equal(body.payload.expected_published_fingerprint,'a'.repeat(64));throw Object.assign(new Error('확인하는 동안 게시본이 변경되었습니다. 다시 비교해 주세요.'),{status:409,code:'workflow_baseline_changed'});};
  h.dialogs.push({action:'reconcile_publication'});h.click('process_actions');await flush();assert.equal(h.writes.length,1);assert.match(h.markup,/다시 비교/);assert.equal(h.draft().definition.nodes.p.instructions,'원래 안내');
});
test('typing during acknowledged publication reconciliation is retained on the new draft revision',async()=>{
  const h=await reconciliationHarness(),pending=deferred();h.writeOverride=()=>pending.promise;h.dialogs.push({action:'reconcile_publication'});h.click('process_actions');await flush();h.change('instructions','기준 확인 중 새 글');const result=h.envelope('EMS','p');result.process.draft_revision=2;result.process.publication_reconciliation.required=false;result.process.publication_reconciliation.can_reconcile=false;pending.resolve(result);await flush();assert.equal(h.draft().definition.nodes.p.instructions,'기준 확인 중 새 글');assert.equal(h.draft().revision,2);assert.equal(h.draft().dirty,true);
});

test('runtime picker reuses exact Native function metadata and generates bounded public inputs locally',async()=>{
 const h=await harness().init();h.click('edit_node',{nodeId:'p-j'});h.dialogs.push({kind:'fixed'});h.click('runtime_config');await flush();
 const reference={tool_id:'native-tool',function:'get_page',revision:2,content_hash:'a'.repeat(64),schema_hash:'b'.repeat(64),config_hash:'c'.repeat(64),environment:'fixture'};
 h.readOverride=route=>route.startsWith('execution/capability?')?{ok:true,capability:{functions:[{name:'get_page',reference,schema:{type:'object',properties:{page_id:{type:'string'}},required:['page_id']},state:'allowed',executable:true}]}}:undefined;
 h.dialogs.push({tool_id:'native-tool'},{function:'get_page'});h.click('runtime_add');await flush();
 const definition=h.draft().definition,call=definition.nodes['p-j'].execution.calls[0];assert.deepEqual(call.reference,reference);assert.deepEqual(call.arguments,{page_id:{source:'input',key:'page_id'}});assert.equal(definition.nodes.p.execution_inputs.properties.page_id.maxLength,2000);assert.deepEqual(definition.nodes.p.execution_inputs.required,['page_id']);assert.equal(h.writes.length,0);assert.equal(Object.values(definition.tools).some(tool=>tool.content),false);
});
test('late Native function metadata cannot modify another workflow after selection changes',async()=>{
 const h=await harness().init();h.click('edit_node',{nodeId:'p-j'});h.dialogs.push({kind:'fixed'});h.click('runtime_config');await flush();const pending=deferred();h.readOverride=route=>route.startsWith('execution/capability?')?pending.promise:undefined;
 h.dialogs.push({tool_id:'native-tool'});h.click('runtime_add');await flush();h.dialogs.push({choice:'keep'});await h.open('q');pending.resolve({ok:true,capability:{functions:[]}});await flush();assert.equal(h.draft().definition.nodes['q-j'].execution,undefined);assert.equal(h.writes.length,0);
});
test('ordinary author sees review metadata but cannot approve Native automation',async()=>{
 const h=await harness().init(),reference={tool_id:'native-tool',function:'get_page',revision:2,content_hash:'a'.repeat(64),schema_hash:'b'.repeat(64),config_hash:'c'.repeat(64),environment:'fixture'};
 h.processes.get('p').workflow.nodes['p-j'].execution={kind:'fixed',calls:[{id:'call',reference,arguments:{}}]};await h.open('p');h.click('edit_node',{nodeId:'p-j'});h.readOverride=route=>route.startsWith('execution/capability?')?{ok:true,capability:{reference,registered:true,state:'unverified',schema:{type:'object'},executable:false}}:undefined;
 h.dialogs.push({});h.click('runtime_review',{callId:'call'});await flush();assert.equal(h.dialogHistory.at(-1).title,'기능 사용 상태');assert.doesNotMatch(h.dialogHistory.at(-1).html,/name="action"|name="evidence"/);assert.equal(h.writes.length,0);
});

test('fresh Native calls omit optional arguments and result binding removes only generated orphan start inputs',async()=>{
 const h=await harness().init(),base={tool_id:'native-tool',revision:2,content_hash:'a'.repeat(64),schema_hash:'b'.repeat(64),config_hash:'c'.repeat(64),environment:'fixture'};
 h.processes.get('p').workflow.nodes.p.execution_inputs={type:'object',properties:{manual:{type:'string',maxLength:20}},required:['manual'],additionalProperties:false};await h.open('p');h.click('edit_node',{nodeId:'p-j'});h.dialogs.push({kind:'fixed'});h.click('runtime_config');await flush();
 const functions=[{name:'search_pages',reference:{...base,function:'search_pages'},schema:{properties:{query:{type:'string'},space_key:{type:'string',default:''},limit:{type:'integer',default:5}},required:['query']},executable:true},{name:'get_page',reference:{...base,function:'get_page'},schema:{properties:{page_id:{type:'string'}},required:['page_id']},executable:true}];
 h.readOverride=route=>{if(!route.startsWith('execution/capability?'))return;const name=new URL('http://fixture/'+route).searchParams.get('function');return {ok:true,capability:name?functions.find(item=>item.name===name):{functions}};};
 for(const name of ['search_pages','get_page']){h.dialogs.push({tool_id:'native-tool'},{function:name});h.click('runtime_add');await flush();}
 let def=h.draft().definition;assert.deepEqual(Object.keys(def.nodes['p-j'].execution.calls[0].arguments),['query']);assert.equal(def.nodes.p.execution_inputs.properties.limit,undefined);assert.equal(def.nodes.p.execution_inputs.properties.space_key,undefined);
 const second=def.nodes['p-j'].execution.calls[1];h.dialogs.push({'source:page_id':'result','result:page_id':'0','path:page_id':'data.results.0.page_id'});h.click('runtime_bind',{callId:second.id});await flush();def=h.draft().definition;
 assert.equal(def.nodes.p.execution_inputs.properties.page_id,undefined);assert.deepEqual(def.nodes.p.execution_inputs.required,['manual','query']);assert.deepEqual(def.nodes.p.execution_inputs.properties.manual,{type:'string',maxLength:20});assert.equal(def.nodes['p-j'].execution.calls[1].arguments.page_id.source,'result');
});
test('author can defer candidate selection without removing its required completion binding or other start inputs',async()=>{
 const h=await harness().init();h.processes.get('p').workflow.nodes.p.execution_inputs={type:'object',properties:{query:{type:'string',maxLength:100},page_id:{type:'string',maxLength:30}},required:['query','page_id'],additionalProperties:false};h.processes.get('p').workflow.nodes['p-j'].execution={kind:'human',completion:{input_key:'page_id'},calls:[]};await h.open('p');
 h.dialogs.push({title:'선택한 문서 번호'});h.click('runtime_input_edit',{inputKey:'page_id'});await flush();const def=h.draft().definition;assert.deepEqual(def.nodes.p.execution_inputs.required,['query']);assert.equal(def.nodes['p-j'].execution.completion.input_key,'page_id');assert.equal(def.nodes.p.execution_inputs.properties.page_id.type,'string');assert.equal(h.writes.length,0);
});

test('typing during ID assignment preserves text and remaps every saved execution dependency for the next save',async()=>{
 const h=harness(),flow=h.processes.get('p').workflow,template=copy(flow.nodes['p-j']),reference={tool_id:'native-tool',function:'get_page',revision:2,content_hash:'a'.repeat(64),schema_hash:'b'.repeat(64),config_hash:'c'.repeat(64),environment:'fixture'};
 const resultRef={job_id:'new-source',call_id:'read',path:['data','version']},choices={job_id:'new-source',call_id:'read',path:['data','results'],value_path:['page_id']};
 flow.nodes['p-t'].children=['new-source','new-target','summary','choice'];delete flow.nodes['p-j'];
 for(const id of flow.nodes['p-t'].children)flow.nodes[id]={...copy(template),id,deps:id==='new-source'?[]:['new-source']};
 flow.nodes['new-source'].execution={kind:'fixed',calls:[{id:'read',reference:copy(reference),arguments:{}}]};
 flow.nodes['new-target'].execution={kind:'fixed',calls:[{id:'detail',reference:copy(reference),arguments:{version:{source:'result',...copy(resultRef)},page_id:{source:'input',key:'page_id',selection:copy(choices)}}}]};
 flow.nodes.summary.execution={kind:'ai',model_id:'model-a',calls:[],evidence:[{job_id:'new-source',call_id:'read'}],completion:{required_claims:[copy(resultRef)]}};
 flow.nodes.choice.execution={kind:'human',calls:[],completion:{input_key:'page_id',choices:copy(choices)}};
 await h.init();h.change('instructions','저장한 안내');
 const pending=deferred();h.writeOverride=()=>pending.promise;h.click('save_draft');await flush();h.change('instructions','저장 응답 중 계속 쓴 안내');
 const response=h.envelope('EMS','p');response.id_map={'new-source':'saved-source','new-target':'saved-target'};response.process.draft_revision=2;
 response.process.workflow=JSON.parse(JSON.stringify(h.writes[0].payload.workflow).replaceAll('new-source','saved-source').replaceAll('new-target','saved-target'));
 pending.resolve(response);await flush();const draft=h.draft();assert.equal(draft.dirty,true);assert.equal(draft.revision,2);assert.equal(draft.definition.nodes.p.instructions,'저장 응답 중 계속 쓴 안내');
 h.writeOverride=async()=>{throw new Error('fixture stops after collecting next save');};h.click('save_draft');await flush();const nodes=h.writes[1].payload.workflow.nodes;
 assert.equal(nodes['new-target'],undefined);assert.deepEqual(nodes['saved-target'].deps,['saved-source']);
 assert.equal(nodes['saved-target'].execution.calls[0].arguments.version.job_id,'saved-source');assert.equal(nodes['saved-target'].execution.calls[0].arguments.page_id.selection.job_id,'saved-source');
 assert.equal(nodes.summary.execution.evidence[0].job_id,'saved-source');assert.equal(nodes.summary.execution.completion.required_claims[0].job_id,'saved-source');assert.equal(nodes.choice.execution.completion.choices.job_id,'saved-source');
 assert.deepEqual(nodes['saved-target'].execution.calls[0].reference,reference);assert.equal(nodes.p.instructions,'저장 응답 중 계속 쓴 안내');
});
