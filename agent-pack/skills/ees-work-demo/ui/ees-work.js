// EES Work offline simulation. No network calls or persistent storage.
(()=>{
const root=document.getElementById('ees-demo-workspace'),q=s=>root.querySelector(s),clone=x=>JSON.parse(JSON.stringify(x)),esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const categoryNames={setup:'셋업',ops:'운영',incident:'장애대응'},levelNames={p:'프로세스 · 전체 업무',t:'태스크 · 단계',j:'잡 · 실행 항목'},marks={p:'P',t:'T',j:'J'},mappingNames={db:'현재 현장의 DB 진단 경로',ap:'현재 현장의 AP 진단 경로',site:'현재 공장·라인 정보',interface:'현재 현장의 연계 정보'},sectionNames={workflow:'업무 절차',skills:'스킬·지침',tools:'도구',sites:'현장 정보'};
let published,draft,version,revision,testedRevision,savedRevision,mode,section,category,selected,editId,assetId,toolId,siteId,cases,caseId,messages,expanded,pinned,navOpen,navCollapsed,epoch=0,newCase=false,previewMode='live',testResults=[],newCounter=0;
function seed(){const b={nodes:{},roots:{setup:['setup-p'],ops:['ops-p'],incident:['incident-p']},tools:{},skills:{},sites:{}};
[['gateway','DB 진단 경로 확인','db','승인된 진단 경로에 접근할 수 있는지 확인'],['db-target','대상 DB 식별','db','요청한 현장과 DB 식별 정보가 일치하는지 확인'],['db-read','읽기 기능 확인','db','승인된 읽기 진단이 정상인지 확인'],['network','AP 네트워크 확인','ap','대상 AP 진단 경로의 접근 상태 확인'],['process','AP 서비스 상태','ap','서비스의 기동 상태 확인'],['health','상태 확인 API','ap','상태 확인 응답이 제한 시간 내 도착하는지 확인'],['smoke','기능 응답 확인','ap','대표 기능의 기대 응답 확인'],['infra','인프라 준비 상태','site','AP·DB 인프라의 준비 항목 확인'],['if-config','연계 설정 확인','interface','대상 시스템의 연계 설정 확인'],['if-round','연계 응답 확인','interface','시스템 간 요청·응답 결과 확인'],['logs','진단 로그 조회','ap','승인된 진단 로그와 오류 요약 확인']].forEach(([id,name,input,purpose])=>b.tools[id]={id,name,input,purpose,type:'진단 API',success:'기대 응답 일치',mockResult:'success',enabled:true});
b.skills={common:{id:'common',name:'공통 실행 지침',type:'instruction',body:'운영 DB에 직접 접근하지 않습니다. 승인된 진단 API·Query Broker를 사용합니다. 실행 결과와 근거를 기록하고 미수행을 성공으로 처리하지 않습니다.',locked:true},setup:{id:'setup',name:'신규 공장 셋업 절차',type:'skill',body:'현장 조건을 확인한 뒤 사전 준비, 인프라 준비, 설치, 연계 검증을 순서대로 진행합니다.'},connection:{id:'connection',name:'연결 점검·실패 분석',type:'skill',body:'필수 점검을 순서대로 수행합니다. 실패하면 후속 의존 점검은 미수행으로 남기고 근거를 제시합니다. 재시도 결과를 이전 결과와 구분합니다.'},handoff:{id:'handoff',name:'검증 결과 정리',type:'skill',body:'완료·실패·미수행 항목과 사용한 근거를 정리하고 다음 행동을 제안합니다.'}};
b.sites={'us-a':{id:'us-a',country:'미국',name:'공장 A',line:'조립 2라인',zone:'America/Chicago',reuse:true,interface:true,db:'US-A DB 진단 경로 · 예시',ap:'US-A AP 진단 경로 · 예시'},'hu-a':{id:'hu-a',country:'헝가리',name:'공장 A',line:'조립 1라인',zone:'Europe/Budapest',reuse:true,interface:false,db:'HU-A DB 진단 경로 · 예시',ap:'HU-A AP 진단 경로 · 예시'},'kr-ca':{id:'kr-ca',country:'한국',name:'천안',line:'조립 2라인',zone:'Asia/Seoul',reuse:false,interface:true,db:'KR-CA DB 진단 경로 · 예시',ap:'KR-CA AP 진단 경로 · 예시'}};
function add(id,type,name,parent,x={}){b.nodes[id]={id,type,name,parent,children:[],description:'',condition:'all',mode:'manual',tools:[],skills:[],bindings:{},deps:[],rule:'필수 항목 모두 확인',...x};if(parent)b.nodes[parent].children.push(id)}
add('setup-p','p','신규 공장 횡전개',null,{category:'setup',description:'현장 조건에 맞춰 시스템을 준비하고 설치·연결·인터페이스 검증 결과를 남깁니다.',skills:['setup'],rule:'필수 잡의 완료와 현장별 적용 조건 확인'});
add('prep-t','t','사전준비','setup-p',{description:'대상과 범위를 확정합니다.'});add('scope-j','j','셋업 범위 확인','prep-t',{description:'대상 공장·라인과 작업 범위를 확인합니다.',rule:'현장과 셋업 범위 확인'});
add('infra-t','t','AP, DB 인프라 준비','setup-p',{description:'사용할 AP·DB 인프라가 준비되어 있는지 확인합니다.'});add('infra-j','j','인프라 준비 확인','infra-t',{mode:'tool',tools:['infra'],bindings:{infra:'site'},deps:['scope-j'],rule:'인프라 준비 항목 모두 통과'});
add('install-t','t','시스템 설치','setup-p',{description:'설치 상태를 확인하고 DB·AP 연결을 검증합니다.',skills:['connection']});add('install-j','j','설치·설정 확인','install-t',{deps:['infra-j'],description:'설치본과 환경 설정이 준비되었는지 확인합니다.',rule:'설치 버전·설정·기동 상태 확인'});
add('db-j','j','DB 연결 확인','install-t',{mode:'tool',tools:['gateway','db-target','db-read'],bindings:{gateway:'db','db-target':'db','db-read':'db'},deps:['install-j'],description:'승인된 진단 경로로 DB 식별과 읽기 기능을 확인합니다.',rule:'필수 DB 점검 모두 통과'});
add('ap-j','j','AP 연결 확인','install-t',{mode:'tool',tools:['network','process','health','smoke'],bindings:{network:'ap',process:'ap',health:'ap',smoke:'ap'},deps:['install-j'],description:'네트워크·서비스·API·기능 응답을 순서대로 점검합니다.',rule:'필수 AP 점검 모두 통과',failOnce:true});
add('interface-t','t','각 시스템간 인터페이스 확인','setup-p',{description:'연계 대상과 요청·응답이 일치하는지 확인합니다.',skills:['handoff']});add('interface-j','j','인터페이스 검증','interface-t',{mode:'tool',tools:['if-config','if-round'],bindings:{'if-config':'interface','if-round':'interface'},condition:'interface',deps:['db-j','ap-j'],rule:'필수 연계 점검 모두 통과'});
add('ops-p','p','일일 시스템 점검',null,{category:'ops',skills:['connection'],description:'업무 시작 전 주요 서비스 상태를 확인합니다.'});add('ops-t','t','서비스 가용성 확인','ops-p');add('ops-j','j','AP 상태 점검','ops-t',{mode:'tool',tools:['network','health','smoke'],bindings:{network:'ap',health:'ap',smoke:'ap'},rule:'서비스 가용성 점검 통과'});
add('incident-p','p','AP 응답 장애 대응',null,{category:'incident',skills:['connection'],description:'장애 증거를 모으고 복구 확인 항목을 진행합니다.'});add('incident-t','t','진단 근거 수집','incident-p');add('incident-j','j','상태·로그 확인','incident-t',{mode:'tool',tools:['network','logs'],bindings:{network:'ap',logs:'ap'},rule:'진단 근거 수집 완료'});add('recovery-t','t','복구 결과 확인','incident-p');add('recovery-j','j','담당자 복구 확인','recovery-t',{deps:['incident-j'],rule:'담당자 조치와 기능 복구 결과 확인'});return b}
function ancestry(nodes, id) {
  const result = [], seen = new Set();
  for (let n = nodes[id]; n && !seen.has(n.id); n = nodes[n.parent]) {
    seen.add(n.id); result.unshift(n);
  }
  return result;
}
function leaves(nodes, id) {
  const n = nodes[id];
  return !n ? [] : n.type === 'j' ? [id] : n.children.flatMap(x => leaves(nodes, x));
}
function c() { return cases[caseId]; }
function snap() { return c().snapshot; }
function jobState(cs, id) {
  return cs.states[id] || (cs.states[id] = {status: 'pending', checks: [], attempt: 0});
}
function applicable(cs, id) {
  return ancestry(cs.snapshot.nodes, id).every(n => n.enabled !== false &&
    (n.condition !== 'interface' || cs.site.interface) &&
    (!n.condition.startsWith('country:') || n.condition.slice(8) === cs.site.country) &&
    (n.condition !== 'reuse' || cs.site.reuse) &&
    (n.condition !== 'new-infra' || !cs.site.reuse) &&
    (!n.condition.startsWith('factory:') || n.condition.slice(8) === cs.site.id) &&
    (!n.condition.startsWith('line:') || n.condition.slice(5) === cs.site.line));
}
function finished(cs, id) {
  const n = cs.snapshot.nodes[id];
  if (!n) return false;
  if (!applicable(cs, id)) return true;
  return n.type === 'j' ? jobState(cs, id).status === 'passed' :
    leaves(cs.snapshot.nodes, id).every(j => finished(cs, j));
}
function count(cs, id) {
  const jobs = leaves(cs.snapshot.nodes, id).filter(j => applicable(cs, j));
  return [jobs.filter(j => finished(cs, j)).length, jobs.length];
}
function dependencies(nodes, id) {
  return [...new Set(ancestry(nodes, id).flatMap(n => n.deps))];
}
function missing(cs, id) {
  return dependencies(cs.snapshot.nodes, id).filter(dep => !finished(cs, dep));
}
function state(cs, id) {
  const n = cs.snapshot.nodes[id];
  if (n.type === 'j') {
    if (!applicable(cs, id)) return 'skipped';
    const result = jobState(cs, id).status;
    return result === 'pending' && missing(cs, id).length ? 'blocked' : result;
  }
  const jobs = leaves(cs.snapshot.nodes, id).filter(j => applicable(cs, j));
  if (!jobs.length) return 'skipped';
  if (jobs.every(j => finished(cs, j))) return 'passed';
  if (jobs.some(j => jobState(cs, j).status === 'running')) return 'running';
  if (jobs.some(j => jobState(cs, j).status === 'failed')) return 'failed';
  if (jobs.every(j => missing(cs, j).length)) return 'blocked';
  return 'pending';
}

const statusNames={pending:'준비 전',blocked:'선행 대기',running:'실행 중',review:'검토 대기',passed:'완료',failed:'실패',skipped:'해당 없음'};function badge(s,label){return'<span class="m-state '+(s==='passed'?'pass':s==='failed'?'fail':s==='running'?'running':'')+'">'+esc(label||statusNames[s]||s)+'</span>'}function context(cs,id){return cs.system+' · '+cs.site.country+' '+cs.site.name+' · '+cs.snapshot.nodes[id].name}
function makeCase(cat='setup',target='us-a',ready=false,sys='EMS'){const id='case-'+(Object.keys(cases).length+1);const cs={id,category:cat,system:sys,version,snapshot:clone(published),site:clone(published.sites[target]),states:{},selected:published.roots[cat][0]};for(const n of Object.values(cs.snapshot.nodes).filter(n=>n.type==='j'))jobState(cs,n.id);if(ready)['scope-j','infra-j','install-j'].forEach(j=>{cs.states[j]={status:'passed',checks:cs.snapshot.nodes[j].tools.map(t=>({id:t,status:'passed',detail:'준비 확인 · 예시'})),attempt:1}});cases[id]=cs;return id}
function init(){epoch++;published=seed();draft=clone(published);version=3;revision=0;testedRevision=-1;savedRevision=0;mode='run';section='workflow';category='setup';selected='setup-p';editId='setup-p';assetId='connection';toolId='health';siteId='us-a';cases={};caseId=makeCase('setup','us-a',true);expanded=new Set(['setup-p','install-t']);pinned=true;navOpen=true;navCollapsed=false;newCase=false;previewMode='live';testResults=[];newCounter=0;q('#m-input').value='';messages=[{role:'user',text:'미국 공장 A의 EMS 셋업 준비 상태와 다음 할 일을 알려줘.',context:'EMS · 미국 공장 A · 신규 공장 횡전개'},{role:'assistant',text:'사전준비, 인프라 준비, 설치 확인까지 완료된 시연 상태예요.\n\n다음은 DB·AP 연결 점검입니다. 각 잡 안의 도구를 순서대로 실행하고, 점검 결과에 따라 완료·실패·미수행을 구분합니다.',context:'EMS · 신규 공장 횡전개'}];renderAll()}
function icons() {
  const paths = {
    layers: 'M3 7 12 2l9 5-9 5Z M3 12l9 5 9-5 M3 17l9 5 9-5',
    'messages-square': 'M3 3h15v12H8l-5 4Z M18 7h3v14l-5-3h-5',
    'sliders-horizontal': 'M3 6h6m4 0h8M3 12h12m4 0h2M3 18h3m4 0h11 M9 3v6m6 0v6M6 15v6',
    activity: 'M2 12h5l3-8 4 16 3-8h5',
    'life-buoy': 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18 M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M5.6 5.6l3.6 3.6m5.6 5.6 3.6 3.6M18.4 5.6l-3.6 3.6m-5.6 5.6-3.6 3.6',
    pin: 'M8 3h8l-1 6 4 5H5l4-5Z M12 14v8',
    plus: 'M12 4v16M4 12h16',
    'arrow-up': 'M12 20V4m-7 7 7-7 7 7',
    'arrow-right': 'M4 12h16m-7-7 7 7-7 7',
    'corner-down-right': 'M4 3v9h16m-6-6 6 6-6 6',
    'book-open': 'M12 5C8 2 4 3 2 4v16c4-2 7-1 10 1 3-2 6-3 10-1V4c-2-1-6-2-10 1Z M12 5v16',
    wrench: 'M14 3a6 6 0 0 0-6 8L2 17l5 5 7-8a6 6 0 0 0 7-7l-4 4-4-4 4-4Z',
    factory: 'M3 21V9l6 4V9l6 4V3h5v18Z M6 17h2m3 0h2m3 0h2',
    pencil: 'M4 16 16 4l4 4L8 20H4Z M14 6l4 4',
    'flask-conical': 'M8 3h8m-6 0v7L3 21h18l-7-11V3 M7 15h10',
    sparkles: 'M12 3l2 7 7 2-7 2-2 7-2-7-7-2 7-2Z',
    workflow: 'M3 3h6v6H3Z M15 15h6v6h-6Z M6 9v9h9 M15 3h6v6h-6Z M9 6h6',
    blocks: 'M3 3h8v8H3Z M13 3h8v8h-8Z M3 13h8v8H3Z M13 13h8v8h-8Z',
    'panel-left': 'M3 3h18v18H3Z M9 3v18',
    'panel-right': 'M3 3h18v18H3Z M15 3v18',
    'layout-panel-top': 'M3 3h18v18H3Z M3 9h18'
  };
  root.querySelectorAll('[data-icon]').forEach(el => {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none'); svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '1.6'); svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round'); svg.setAttribute('aria-hidden', 'true');
    const path = document.createElementNS(svg.namespaceURI, 'path');
    path.setAttribute('d', paths[el.dataset.icon] || paths.blocks);
    svg.append(path); el.replaceWith(svg);
  });
}function setText(id,text){const el=q('#'+id);if(el)el.textContent=text}function append(role,text,cs=c(),id=selected){messages.push({role,text,context:context(cs,id)});renderMessages()}function renderMessages(){q('#m-messages').innerHTML=messages.map(m=>'<article class="msg '+m.role+'">'+(m.role==='assistant'?'<div class="message-author"><i data-icon="sparkles" aria-hidden="true"></i>Assistant</div>':'')+'<p>'+esc(m.text)+'</p><small class="message-context">'+esc(m.context)+'</small></article>').join('');icons()}
function nodeTree(nodes,id,design){const n=nodes[id],open=expanded.has(id),active=design?editId:selected;return'<div class="node-line '+(active===id?'selected':'')+'">'+(n.children.length?'<button class="expand" data-expand="'+id+'" aria-expanded="'+open+'" aria-label="'+esc(n.name)+(open?' 접기':' 펼치기')+'">'+(open?'⌄':'›')+'</button>':'<span class="node-spacer"></span>')+'<button class="select-node" data-'+(design?'edit-node':'node')+'="'+id+'" '+(active===id?'aria-current="page"':'')+'><span class="node-dot">'+marks[n.type]+'</span><span class="label">'+esc(n.name)+'</span></button></div>'+(open?'<div class="children">'+n.children.map(x=>nodeTree(nodes,x,design)).join('')+'</div>':'')}
function renderNav(){q('#m-run-tree').innerHTML=snap().roots[category].map(id=>nodeTree(snap().nodes,id,false)).join('');q('#m-case').innerHTML=Object.values(cases).map(cs=>'<option value="'+cs.id+'" '+(cs.id===caseId?'selected':'')+'>'+categoryNames[cs.category]+' · '+cs.system+' · '+cs.site.country+' '+cs.site.name+' · v1.'+cs.version+'</option>').join('');q('#m-design-tree').innerHTML=section==='workflow'?Object.entries(draft.roots).map(([cat,ids])=>'<small class="muted">'+categoryNames[cat]+'</small>'+ids.map(id=>nodeTree(draft.nodes,id,true)).join('')).join(''):'<div class="nav-legend">공용 자산을 편집하고 업무에 연결합니다.</div>';q('#m-navigator').hidden=!navOpen;q('#m-app').classList.toggle('unpinned',!pinned&&mode==='run'&&!navCollapsed);q('#m-app').classList.toggle('nav-collapsed',navCollapsed);setText('m-pin-text',pinned?'고정됨':'고정');q('#m-pin').setAttribute('aria-pressed',String(pinned));root.querySelectorAll('[data-category]').forEach(b=>b.classList.toggle('active',b.dataset.category===category));root.querySelectorAll('[data-section]').forEach(b=>b.classList.toggle('active',b.dataset.section===section))}
function renderBreadcrumb(){q('#m-breadcrumb').innerHTML=mode==='run'?'<button data-show-nav="true">'+categoryNames[category]+'</button><span class="sep">›</span><span class="muted m-small-text">'+c().system+'</span>'+ancestry(snap().nodes,selected).map(n=>'<span class="sep">›</span><button data-node="'+n.id+'" class="'+(selected===n.id?'current':'')+'">'+esc(n.name)+'</button>').join(''):'<span class="muted">설계 워크스페이스</span><span class="sep">›</span><span>'+sectionNames[section]+'</span>'}
function renderAll(){q('#m-run-nav').hidden=mode!=='run';q('#m-design-nav').hidden=mode!=='design';q('#m-run-panes').hidden=mode!=='run';q('#m-design-panes').hidden=mode!=='design';q('#m-new-case').hidden=mode!=='run';q('#m-run-mode').classList.toggle('active',mode==='run');q('#m-design-mode').classList.toggle('active',mode==='design');setText('m-screen-title',mode==='run'?categoryNames[category]+' 협업':'설계 워크스페이스');renderNav();renderBreadcrumb();if(mode==='run'){renderWork();renderMessages()}else renderDesigner();icons()}
function choose(id){if(!snap().nodes[id])return;selected=id;c().selected=id;category=ancestry(snap().nodes,id)[0].category;newCase=false;ancestry(snap().nodes,id).forEach(n=>expanded.add(n.id));if(!pinned)navOpen=false;renderBreadcrumb();renderNav();renderWork()}
function nextJob(cs,id){const jobs=leaves(cs.snapshot.nodes,id);const unfinished=jobs.find(j=>!finished(cs,j));if(!unfinished)return null;function seek(j,seen=new Set()){if(seen.has(j))return j;seen.add(j);const pre=missing(cs,j);return pre.length?seek(leaves(cs.snapshot.nodes,pre[0]).find(x=>!finished(cs,x))||pre[0],seen):j}return seek(unfinished)}function effectiveSkills(cs,id){return [...new Set(['common',...ancestry(cs.snapshot.nodes,id).flatMap(n=>n.skills)])].map(k=>cs.snapshot.skills[k]).filter(Boolean)}
function caseContext(cs){return'<div class="m-case-context"><strong>'+esc(cs.site.country+' · '+cs.site.name+' · '+cs.site.line)+'</strong><small>'+cs.system+' · '+(cs.site.reuse?'기존 인프라 재사용':'신규 인프라 준비')+' · 적용 절차 v1.'+cs.version+'</small></div>'}
function nextCard(cs,id){const next=nextJob(cs,id);if(!next&&count(cs,id)[1]===0)return'<div class="next-step"><small class="eyebrow">적용 대상 없음</small><strong>이 현장에서는 필수 작업이 제외됩니다.</strong><p>제외 항목은 성공 건수에 포함하지 않습니다.</p><button data-action="summary">결과 요약 보기</button></div>';if(!next)return'<div class="next-step"><small class="eyebrow">필수 작업 완료</small><strong>적용된 검증을 모두 마쳤어요.</strong><p>점검 결과와 제외 사유를 확인할 수 있습니다.</p><button data-action="summary">결과 요약 보기</button></div>';const n=cs.snapshot.nodes[next],s=state(cs,next);return'<div class="next-step"><small class="eyebrow">지금 할 일</small><strong>'+esc(n.name)+'</strong><p>'+(s==='failed'?'실패한 점검과 미수행 항목을 확인하고 재시도하세요.':n.mode==='tool'?'선행 조건을 마쳤습니다. 연결된 점검을 실행할 수 있어요.':'담당자가 준비 내용을 확인해 주세요.')+'</p><button class="primary" data-node="'+next+'">'+(s==='failed'?'실패 결과 열기':'작업 열기')+'<i data-icon="arrow-right" aria-hidden="true"></i></button></div>'}
function rows(cs,id){const nodes=cs.snapshot.nodes;return'<div class="work-list">'+nodes[id].children.map((key,i)=>{const n=nodes[key],s=state(cs,key),[d,t]=count(cs,key);const info=n.type==='j'?(!applicable(cs,key)?exclusionReason(cs,key):missing(cs,key).length?'선행: '+missing(cs,key).map(x=>nodes[x].name).join(', '):n.mode==='tool'?n.tools.length+'개 점검 · 자동 판정':'담당자 확인'):t?d+'/'+t+'개 잡 완료':'현장 조건으로 제외';return'<button class="task-row" data-node="'+key+'"><span class="task-number '+(s==='passed'?'finished':'')+'">'+(s==='passed'?'✓':i+1)+'</span><span class="task-label"><strong>'+esc(n.name)+'</strong><small>'+esc(info)+'</small></span>'+badge(s)+'</button>'}).join('')+'</div>'}
function workHeader(cs,id){const n=cs.snapshot.nodes[id];return'<div class="panel-meta"><span>'+levelNames[n.type]+'</span>'+badge(state(cs,id))+'</div><h2>'+esc(n.name)+'</h2><p class="panel-intro">'+esc(n.description||'선행 조건과 완료 기준에 따라 업무를 진행합니다.')+'</p>'+caseContext(cs)+(cs.system!=='EMS'?'<div class="notice">'+esc(cs.system)+' 전문가 절차는 예시 템플릿입니다. 실제 시스템별 검증은 구현하지 않았습니다.</div>':'')}
function contract(cs,id){const n=cs.snapshot.nodes[id];return'<details class="m-run-contract"><summary>적용 스킬·지침·실행 기준</summary><div class="m-contract-body"><strong>'+esc(n.rule)+'</strong>'+effectiveSkills(cs,id).map(s=>'<div><span>'+esc(s.name)+'</span><small class="m-display-block">'+esc(s.body)+'</small></div>').join('')+'<small>설정과 현장 조건은 이 셋업을 시작할 때 고정되었습니다.</small></div></details>'}
function renderWork(){
  setText('m-chat-context',context(c(),selected));
  if(newCase){renderNewCase();return}
  const cs=c(),n=cs.snapshot.nodes[selected];
  let body=workHeader(cs,selected);
  if(n.type!=='j'){
    const[d,t]=count(cs,selected);
    body+=nextCard(cs,selected)+'<div class="section-row"><strong>'+(n.type==='p'?'진행 단계':'잡과 실행 조건')+'</strong><small>필수 잡 '+d+' / '+t+' 완료</small></div><progress class="progress-track" aria-label="필수 잡 완료" value="'+d+'" max="'+(t||1)+'">'+d+' / '+t+'</progress>'+rows(cs,selected)+contract(cs,selected);
  }else{
    const st=jobState(cs,selected),blocked=missing(cs,selected);
    if(!applicable(cs,selected)){
      body+='<div class="m-status">적용 제외 · '+esc(exclusionReason(cs,selected))+'</div>';
    }else if(n.mode==='tool'){
      body+='<div class="section-row"><strong>자동 점검</strong><small>'+n.tools.length+'개 도구 · '+st.attempt+'회 실행</small></div><div class="m-checks">'+n.tools.map((t,i)=>{
        const res=st.checks[i]||{status:'pending',detail:'실행 대기'},tool=cs.snapshot.tools[t];
        return'<div class="m-check"><div class="m-check-head"><strong>'+String(i+1).padStart(2,'0')+' · '+esc(tool?.name||'미등록 도구')+'</strong>'+badge(res.status,res.status==='skipped'?'미수행':res.status==='passed'?'통과':null)+'</div><small>입력 · '+esc(inputValue(cs,n,t))+'</small><p>'+esc(res.detail)+'</p></div>';
      }).join('')+'</div>';
      if(st.status==='failed')body+='<div class="m-status failure" role="status">잡 실패 · 후속 의존 점검은 미수행으로 남깁니다. 상위 태스크도 완료되지 않습니다.</div>';
      if(st.status==='passed')body+='<div class="m-status" role="status">필수 점검과 성공 기준을 모두 통과했습니다.</div>';
      if(blocked.length)body+='<div class="notice blocked">먼저 완료할 작업: '+blocked.map(x=>'<button class="material-button" data-node="'+x+'">'+esc(cs.snapshot.nodes[x].name)+'</button>').join(', ')+'</div>';
      body+='<div class="m-job-actions"><button class="primary" data-action="run" '+(st.status==='running'||blocked.length?'disabled':'')+'>'+(st.status==='running'?'자동 점검 진행 중':st.attempt?'재시도 · 시뮬레이션':'점검 실행 · 시뮬레이션')+'</button></div>'+runHistory(st,cs)+contract(cs,selected);
    }else if(n.mode==='draft'){
      body+='<div class="m-document"><small>문서 초안 · 예시</small>'+(st.document?'<p class="m-draft-body">'+esc(st.document)+'</p>':'<p>연결한 스킬과 현장 정보를 바탕으로 검토용 초안을 작성합니다.</p>')+'</div><div class="m-job-actions"><button data-action="generate-draft" '+(blocked.length?'disabled':'')+'>'+(st.document?'초안 다시 작성':'초안 만들기')+'</button><button class="primary" data-action="manual" '+(!st.document||blocked.length||st.status==='passed'?'disabled':'')+'>'+(st.status==='passed'?'검토 완료':'검토 완료 · 예시')+'</button></div>'+contract(cs,selected);
    }else{
      body+='<div class="evidence-summary"><strong>확인할 내용</strong><p>'+esc(n.rule)+'</p><small>'+esc(n.description||'대상과 근거 자료를 확인합니다.')+'</small></div><div class="m-job-actions"><button class="primary" data-action="manual" '+(blocked.length||st.status==='passed'?'disabled':'')+'>'+(st.status==='passed'?'확인 완료':'내용 확인 완료 · 예시')+'</button></div>'+(blocked.length?'<div class="notice">선행 작업 완료 후 확인할 수 있습니다.</div>':'')+contract(cs,selected);
    }
  }
  q('#m-work-content').innerHTML=body;icons();
}
function exclusionReason(cs,id){const path=ancestry(cs.snapshot.nodes,id);if(path.some(n=>n.enabled===false))return'설계에서 사용하지 않는 업무';if(path.some(n=>n.condition==='interface')&&!cs.site.interface)return'이 현장은 시스템 간 연계를 사용하지 않음';if(path.some(n=>n.condition==='reuse')&&!cs.site.reuse)return'신규 인프라 현장으로 재사용 점검 제외';if(path.some(n=>n.condition==='new-infra')&&cs.site.reuse)return'기존 인프라 재사용으로 신규 준비 제외';return'업무에 지정된 국가·공장·라인 조건과 현재 현장이 다름'}
function inputValue(cs,node,toolId){const input=node.bindings[toolId]||cs.snapshot.tools[toolId]?.input;return input==='db'?cs.site.db:input==='ap'?cs.site.ap:input==='interface'?cs.system+' · '+cs.site.country+' '+cs.site.name+' 연계':cs.site.country+' '+cs.site.name+' · '+cs.site.line}
function runHistory(st,cs){return(st.history||[]).length?'<details class="m-run-contract"><summary>이전 실행 결과 · '+st.history.length+'회</summary><div class="m-contract-body">'+st.history.map(h=>'<div><strong>'+h.attempt+'회차 · '+(h.status==='failed'?'실패':h.status==='passed'?'완료':'중단')+'</strong><small class="m-display-block">'+esc(h.reason||'이전 실행')+'</small>'+h.checks.map(r=>'<small class="m-display-block">'+esc(cs.snapshot.tools[r.id]?.name||r.id)+' · '+(r.status==='skipped'?'미수행':statusNames[r.status])+' · '+esc(r.detail)+'</small>').join('')+'</div>').join('')+'</div></details>':''}
function invalidate(cs,id){const affected=new Set([id]);let changed=true;while(changed){changed=false;Object.values(cs.snapshot.nodes).filter(n=>n.type==='j').forEach(n=>{if(!affected.has(n.id)&&dependencies(cs.snapshot.nodes,n.id).some(p=>leaves(cs.snapshot.nodes,p).some(j=>affected.has(j)))){affected.add(n.id);changed=true}})}for(const key of affected){const before=jobState(cs,key),history=clone(before.history||[]);if(before.checks.length||['passed','review','running'].includes(before.status))history.push({attempt:before.attempt,status:before.status,checks:clone(before.checks),document:before.document||null,reason:key===id?'재실행':'선행 작업 재실행으로 무효화'});cs.states[key]={status:'pending',checks:[],attempt:before.attempt,history}}}
async function runJob(id=selected){const cs=c(),n=cs.snapshot.nodes[id],token=epoch;if(n.type!=='j'){const next=nextJob(cs,id);if(next)choose(next);return}if(!applicable(cs,id)){append('assistant','이 현장에서는 적용 제외된 작업입니다.',cs,id);return}if(missing(cs,id).length){append('assistant','선행 작업을 먼저 완료해 주세요: '+missing(cs,id).map(dep=>cs.snapshot.nodes[dep].name).join(', '),cs,id);return}if(jobState(cs,id).status==='running')return;if(n.mode==='draft'){generateDraft(id);return}if(n.mode!=='tool'){manual(id);return}invalidate(cs,id);const st=jobState(cs,id);st.attempt++;st.status='running';st.checks=n.tools.map(t=>({id:t,status:'pending',detail:'실행 대기'}));const shouldFail=n.failOnce&&st.attempt===1;function refresh(){if(epoch===token&&caseId===cs.id){renderNav();if(mode==='run')renderWork()}}
let failed=false;refresh();for(let i=0;i<n.tools.length;i++){if(epoch!==token||cs.states[id]!==st)return;const tool=cs.snapshot.tools[n.tools[i]],item=st.checks[i];if(failed){item.status='skipped';item.detail='앞선 필수 점검 실패로 미수행';refresh();continue}item.status='running';item.detail='예시 응답 확인 중';refresh();await new Promise(resolve=>setTimeout(resolve,260));if(epoch!==token||cs.states[id]!==st)return;if(!tool?.enabled){item.status='failed';item.detail='연결된 실행 어댑터 없음';failed=true}else if((n.bindings[n.tools[i]]||tool.input)!==tool.input){item.status='failed';item.detail='도구가 요구하는 입력값 종류와 연결된 입력이 다름';failed=true}else if(tool.mockResult==='failure'){item.status='failed';item.detail='등록된 모의 응답: 실패';failed=true}else if(shouldFail&&n.tools[i]==='health'){item.status='failed';item.detail='응답 시간 초과 · 시연용 실패 결과';failed=true}else{item.status='passed';item.detail=n.tools[i]==='db-target'?'요청한 현장과 DB 식별 일치 · 예시':n.tools[i]==='db-read'?'승인된 읽기 진단 정상 · 예시':n.tools[i]==='logs'?'승인된 진단 로그 요약 확보 · 예시':n.tools[i]==='infra'?(cs.site.reuse?'기존 AP·DB 인프라 재사용 상태 확인 · 예시':'신규 AP·DB 인프라 준비 상태 확인 · 예시'):'기대 응답과 일치 · 예시'}refresh()}if(epoch!==token||cs.states[id]!==st)return;st.status=failed?'failed':'passed';refresh();append('assistant',failed?n.name+'에서 필수 점검이 실패한 예시입니다. 후속 의존 점검은 미수행으로 남겼어요. 실패 근거를 확인한 뒤 재시도할 수 있습니다.':n.name+'의 필수 점검이 모두 통과한 예시입니다. 상위 진행 상황에도 반영했어요.',cs,id)}
function manual(id=selected){const cs=c(),n=cs.snapshot.nodes[id],st=jobState(cs,id);if(n.type!=='j'||n.mode==='tool'||st.status==='passed'||missing(cs,id).length||!applicable(cs,id)||n.mode==='draft'&&!st.document)return;st.attempt=Math.max(1,st.attempt);st.status='passed';renderWork();renderNav();append('assistant',n.name+'의 담당자 확인을 기록한 예시입니다.',cs,id)}
function generateDraft(id=selected){const cs=c(),n=cs.snapshot.nodes[id];if(n.type!=='j'||n.mode!=='draft'||missing(cs,id).length||!applicable(cs,id))return;invalidate(cs,id);const st=jobState(cs,id);st.attempt++;st.document=cs.site.country+' '+cs.site.name+' · '+cs.system+'\n\n작업: '+n.name+'\n목표: '+(n.description||n.rule)+'\n\n검토할 기준\n'+n.rule+'\n\n적용 스킬·지침\n'+effectiveSkills(cs,id).map(s=>s.name).join(' · ')+'\n\n담당자가 검토한 뒤 완료를 기록합니다.';st.status='review';renderWork();renderNav();append('assistant',n.name+'의 문서 초안을 만든 예시입니다. 오른쪽에서 내용을 검토해 주세요.',cs,id)}
function renderNewCase(){const opts=Object.values(published.sites).map(s=>'<option value="'+s.id+'">'+esc(s.country+' · '+s.name)+'</option>').join('');q('#m-work-content').innerHTML='<div class="m-newcase"><div class="panel-meta">새 셋업 준비</div><h2>현장에 맞는 절차 구성</h2><label class="m-field">시스템<select id="m-start-system"><option>EMS</option><option>APC</option><option>FDC</option><option>EGIS</option><option>EPT</option></select></label><label class="m-field">대상 현장<select id="m-start-site">'+opts+'</select></label><div id="m-site-plan"></div><button class="primary" data-action="create-case">이 조건으로 시작 · 예시</button><button data-action="cancel-case">진행 중인 작업으로 돌아가기</button></div>';updateSitePlan()}
function updateSitePlan(){const site=published.sites[q('#m-start-site').value||Object.keys(published.sites)[0]];q('#m-site-plan').innerHTML='<div class="evidence-summary"><strong>적용 절차 v1.'+version+'</strong><span>'+esc(site.line)+' · '+(site.reuse?'기존 인프라 재사용':'신규 인프라 준비')+'</span><span>'+(site.interface?'시스템 간 인터페이스 검증 포함':'연계 미사용: 인터페이스 검증 제외')+'</span><small>조건과 버전을 고정하고 새 진행 상태로 시작합니다. 시스템별 전문가 절차는 예시 템플릿입니다.</small></div>'}
function switchCategory(cat){category=cat;navOpen=true;navCollapsed=false;let cs=Object.values(cases).find(x=>x.category===cat);if(!cs){const id=makeCase(cat,'us-a',false);cs=cases[id]}caseId=cs.id;selected=cs.selected;newCase=false;ancestry(snap().nodes,selected).forEach(n=>expanded.add(n.id));renderAll()}
function changeMode(value){mode=value;navCollapsed=false;if(mode==='design'){section='workflow';editId=draft.nodes[selected]?selected:'setup-p';previewMode='live'}renderAll()}
function field(label,prop,value,kind='node',multiline=false,locked=false){return'<label class="m-field">'+label+(multiline?'<textarea data-kind="'+kind+'" data-field="'+prop+'" '+(locked?'readonly':'')+'>'+esc(value)+'</textarea>':'<input type="text" data-kind="'+kind+'" data-field="'+prop+'" value="'+esc(value)+'" '+(locked?'readonly':'')+'>')+'</label>'}function options(values,value){return values.map(([v,label])=>'<option value="'+esc(v)+'" '+(v===value?'selected':'')+'>'+esc(label)+'</option>').join('')}function skillBindings(n){return'<fieldset class="m-fieldset"><legend>적용 스킬·지침</legend><label class="m-option"><input type="checkbox" checked disabled><span>공통 실행 지침<small class="m-display-block">모든 업무에 항상 적용</small></span></label>'+Object.values(draft.skills).filter(s=>!s.locked).map(s=>'<label class="m-option"><input type="checkbox" data-bind-skill="'+s.id+'" '+(n.skills.includes(s.id)?'checked':'')+'><span>'+esc(s.name)+'<small class="m-display-block">'+(s.type==='skill'?'스킬':'지침')+'</small></span></label>').join('')+'</fieldset>'}
function toolBindings(n){return'<fieldset class="m-fieldset"><legend>'+(n.type==='j'?'실행할 도구 · 위에서부터 순서대로':'사용 가능한 도구 · 미지정 시 공통 범위')+'</legend>'+n.tools.map((id,i)=>'<div class="m-binding"><div class="m-binding-head"><strong class="m-small-text">'+(i+1)+'. '+esc(draft.tools[id]?.name||'미등록 도구')+'</strong><div><button data-tool-up="'+i+'" '+(i===0?'disabled':'')+' aria-label="도구 순서 위로">↑</button><button data-tool-remove="'+i+'">해제</button></div></div><label class="m-field">입력 연결<select data-map-input="'+id+'">'+options(Object.entries(mappingNames),n.bindings[id]||draft.tools[id]?.input||'site')+'</select></label></div>').join('')+'<label class="m-field">도구 추가<select id="m-tool-to-add"><option value="">등록된 도구 선택</option>'+Object.values(draft.tools).filter(t=>!n.tools.includes(t.id)).map(t=>'<option value="'+t.id+'">'+esc(t.name)+'</option>').join('')+'</select></label><button class="m-test-button" data-action="add-tool-binding">선택한 도구 연결</button></fieldset>'}
function nodeForm() {
  const n = draft.nodes[editId], rootId = ancestry(draft.nodes, editId)[0].id;
  const peers = n.type === 'p' ? draft.roots[n.category] : Object.values(draft.nodes)
    .filter(x => x.type === n.type && ancestry(draft.nodes,x.id)[0].id === rootId).map(x => x.id);
  const prerequisites = peers.filter(id => id !== editId);
  const order = n.parent ? draft.nodes[n.parent].children : draft.roots[n.category];
  const index = order.indexOf(editId);
  return '<div class="m-node-actions"><button data-action="new-process">프로세스 추가</button>' +
    '<button data-action="add-child" '+(n.type==='j'?'disabled':'')+'>'+(n.type==='p'?'태스크 추가':'잡 추가')+'</button>' +
    '<button data-action="move-up" '+(index===0?'disabled':'')+'>위로 이동</button>' +
    '<button data-action="move-down" '+(index===order.length-1?'disabled':'')+'>아래로 이동</button></div>' +
    '<div class="panel-meta">'+levelNames[n.type]+'</div><div class="m-form">' +
    field('이름','name',n.name)+field('목표·작업 설명','description',n.description,'node',true) +
    '<label class="m-field">적용 조건<select data-kind="node" data-field="condition">' +
    options([['all','모든 현장'],['interface','시스템 간 연계를 사용하는 현장'],
      ['reuse','기존 AP·DB 인프라 재사용 현장'],['new-infra','신규 AP·DB 인프라 준비 현장'],
      ...Object.values(draft.sites).map(site=>['factory:'+site.id,site.country+' '+site.name+' 현장']),
      ...Array.from(new Set(Object.values(draft.sites).map(site=>site.line))).map(line=>['line:'+line,line+' 적용']),
      ['country:미국','미국 현장'],['country:한국','한국 현장'],['country:헝가리','헝가리 현장']],n.condition) +
    '</select></label><label class="m-option"><input type="checkbox" data-kind="node" data-field="enabled" '+
    (n.enabled!==false?'checked':'')+'>이 업무 사용</label>' +
    (n.type==='j'?'<label class="m-field">수행 방식<select data-kind="node" data-field="mode">'+
      options([['manual','사람 확인'],['tool','등록 도구 점검 · 모의 실행'],['draft','AI 초안 작성']],n.mode)+'</select></label>':'') +
    '<details class="m-fieldset"><summary>선행 작업 · '+n.deps.length+'개</summary>' +
    (prerequisites.length?prerequisites.map(id=>'<label class="m-option"><input type="checkbox" data-bind-dep="'+id+'" '+
      (n.deps.includes(id)?'checked':'')+'>'+esc(draft.nodes[id].name)+'</label>').join(''):'<small>같은 단계의 다른 업무를 추가하면 선택할 수 있습니다.</small>') +
    '</details>'+toolBindings(n)+skillBindings(n)+field('완료 기준','rule',n.rule,'node',true)+'</div>';
}

function assetsForm(){const a=draft.skills[assetId]||Object.values(draft.skills)[0];assetId=a.id;return'<div class="m-asset-select"><select aria-label="편집할 스킬·지침" data-select-asset="true">'+options(Object.values(draft.skills).map(s=>[s.id,s.name]),assetId)+'</select><button data-action="new-skill">새로 만들기</button></div><div class="m-form">'+field('이름','name',a.name,'skill',false,a.locked)+'<label class="m-field">종류<select data-kind="skill" data-field="type" '+(a.locked?'disabled':'')+'>'+options([['skill','스킬 · 절차와 판단 기준'],['instruction','지침 · 공통 또는 추가 규칙']],a.type)+'</select></label>'+field('내용','body',a.body,'skill',true,a.locked)+(a.locked?'<small>공통 실행 지침은 하위 업무에서 해제되지 않습니다.</small>':'<button data-action="skill-draft" class="m-test-button">AI로 내용 초안 만들기 · 예시</button>')+'</div>'}
function toolsForm(){const t=draft.tools[toolId]||Object.values(draft.tools)[0];toolId=t.id;return'<div class="m-asset-select"><select aria-label="편집할 도구" data-select-tool="true">'+options(Object.values(draft.tools).map(t=>[t.id,t.name]),toolId)+'</select><button data-action="new-tool">도구 등록</button></div><div class="m-form">'+field('도구 이름','name',t.name,'tool')+field('하는 일','purpose',t.purpose,'tool',true)+'<label class="m-field">도구 종류<select data-kind="tool" data-field="type">'+options([['진단 API','진단 API'],['스크립트','스크립트']],t.type)+'</select></label><label class="m-field">입력값 종류<select data-kind="tool" data-field="input">'+options(Object.entries(mappingNames),t.input)+'</select></label>'+field('성공 기준','success',t.success,'tool')+'<label class="m-field">모의 응답<select data-kind="tool" data-field="mockResult">'+options([['success','성공 응답 예시'],['failure','실패 응답 예시']],t.mockResult||'success')+'</select></label>'+'<label class="m-option"><input type="checkbox" data-kind="tool" data-field="enabled" '+(t.enabled?'checked':'')+'><span>시연 어댑터 연결<small class="m-display-block">예시 응답만 반환하며 실제 코드·API는 실행하지 않음</small></span></label><button data-action="test-tool" class="m-test-button">이 도구 시험 · 예시</button></div>'}
function sitesForm(){const s=draft.sites[siteId]||Object.values(draft.sites)[0];siteId=s.id;return'<div class="m-asset-select"><select aria-label="편집할 현장" data-select-site="true">'+options(Object.values(draft.sites).map(s=>[s.id,s.country+' · '+s.name]),siteId)+'</select><button data-action="new-site">현장 추가</button></div><div class="m-form"><label class="m-field">국가<select data-kind="site" data-field="country">'+options([['미국','미국'],['한국','한국'],['헝가리','헝가리']],s.country)+'</select></label>'+field('공장','name',s.name,'site')+field('라인','line',s.line,'site')+field('시간대','zone',s.zone,'site')+'<label class="m-option"><input type="checkbox" data-kind="site" data-field="reuse" '+(s.reuse?'checked':'')+'>기존 AP·DB 인프라 재사용</label><label class="m-option"><input type="checkbox" data-kind="site" data-field="interface" '+(s.interface?'checked':'')+'>시스템 간 연계 사용</label>'+field('DB 진단 경로 이름','db',s.db,'site')+field('AP 진단 경로 이름','ap',s.ap,'site')+'<small>인증값과 실제 접속 주소는 이 목업에 입력하지 않습니다.</small></div>'}
function renderDesigner(){setText('m-design-title',sectionNames[section]);setText('m-draft-version','v1.'+(version+1)+' 초안'+(revision!==savedRevision?' · 저장 전 변경 있음':''));q('#m-designer-content').innerHTML=section==='workflow'?nodeForm():section==='skills'?assetsForm():section==='tools'?toolsForm():sitesForm();q('#m-design-status').hidden=true;renderPreview();icons()}
function previewWorkflow() {
  const n=draft.nodes[editId], site=draft.sites[siteId]||Object.values(draft.sites)[0];
  const previewCase={snapshot:draft,site,system:'EMS',states:{}};
  const skills=[...new Set(['common',...ancestry(draft.nodes,editId).flatMap(x=>x.skills)])];
  const excluded=!applicable(previewCase,editId);
  return '<label class="m-field m-preview-site">미리볼 현장<select data-preview-site="true">'+
    options(Object.values(draft.sites).map(x=>[x.id,x.country+' · '+x.name+' · '+x.line]),site.id)+'</select></label>'+
    '<div class="m-preview-card"><div class="panel-meta">'+levelNames[n.type]+'</div><h2>'+esc(n.name)+'</h2>'+
    '<p>'+esc(n.description||'작업 설명을 입력하면 이곳에 표시됩니다.')+'</p>'+
    '<div class="m-case-context"><strong>'+esc(site.country+' · '+site.name+' · '+site.line)+'</strong><small>'+
    (site.reuse?'기존 AP·DB 인프라 재사용':'신규 AP·DB 인프라 준비')+'</small></div>'+
    (excluded?'<div class="m-status">적용 제외 · '+esc(exclusionReason(previewCase,editId))+'</div>':'')+
    (n.type==='j'?'<strong>'+(n.mode==='draft'?'AI 초안 작성 · 담당자 검토':n.mode==='manual'?'담당자 확인':'실행할 점검 · '+n.tools.length+'개')+'</strong>'+
      n.tools.map((id,i)=>'<div class="m-preview-row"><span>'+(i+1)+'. '+esc(draft.tools[id]?.name||'미등록 도구')+
      '<small class="m-display-block">'+esc(inputValue(previewCase,n,id))+'</small></span>'+
      badge(draft.tools[id]?.enabled?'pending':'failed',draft.tools[id]?.enabled?'연결됨':'미연결')+'</div>').join(''):
      '<strong>하위 작업 · '+n.children.length+'개</strong>'+n.children.map(id=>'<div class="m-preview-row"><span>'+marks[draft.nodes[id].type]+
        ' · '+esc(draft.nodes[id].name)+'</span>'+(!applicable(previewCase,id)?badge('skipped','적용 제외'):'<span>›</span>')+'</div>').join(''))+
    '<strong>완료 기준</strong><p>'+esc(n.rule)+'</p><strong>적용 스킬·지침</strong><p>'+skills.map(id=>esc(draft.skills[id]?.name||'삭제된 자산')).join(' · ')+
    '</p></div><p class="m-quiet-note">미리보기와 시험은 예시입니다. 진행 중인 셋업의 절차·현장 조건·결과는 기존 버전을 유지합니다.</p>';
}

function renderPreview(){let title='사용자 화면 미리보기',html='';if(previewMode==='test'){title='시험 결과 · 시뮬레이션';html=testResults.map(t=>'<div class="m-test-result"><div><strong>'+esc(t.name)+'</strong><small>'+esc(t.detail)+'</small></div>'+badge(t.pass?'passed':'failed',t.pass?'통과':'수정 필요')+'</div>').join('')+'<p class="m-quiet-note">구조·참조와 예시 응답을 확인합니다. 사내 실행 검증이 아닙니다.</p>'}else if(previewMode==='publish'){title='게시 전 변경 확인';const changed=changes();html='<div class="m-preview-card"><h2>v1.'+(version+1)+' 게시</h2><p>이번 초안의 변경을 새 셋업부터 적용합니다.</p>'+changed.map(x=>'<div class="m-preview-row">'+esc(x)+'</div>').join('')+'<small>진행 중인 '+c().site.country+' '+c().site.name+' 셋업은 v1.'+c().version+'을 유지합니다.</small><button class="primary" data-action="confirm-publish">이 변경 게시 · 시뮬레이션</button><button data-action="preview-live">미리보기로 돌아가기</button></div>'}else if(previewMode==='published'){title='게시 완료 · 예시';html='<div class="m-preview-card"><h2>v1.'+version+' 게시됨</h2><p>새 셋업은 이 버전을 사용합니다. 진행 중인 작업은 기존 버전을 유지합니다.</p><button class="primary" data-action="new-case-after-publish">새 버전으로 셋업 준비</button><button data-action="preview-live">계속 설계하기</button></div>'}else if(section==='workflow')html=previewWorkflow();else if(section==='skills'){const a=draft.skills[assetId];title='적용될 내용';html='<div class="m-preview-card"><small>'+(a.type==='skill'?'스킬':'지침')+'</small><h2>'+esc(a.name)+'</h2><p>'+esc(a.body||'아직 내용이 없습니다.')+'</p><small>연결한 업무를 수행할 때 필요한 내용을 제공합니다.</small></div>'}else if(section==='tools'){const t=draft.tools[toolId];title='도구 등록 미리보기';html='<div class="m-preview-card"><h2>'+esc(t.name)+'</h2>'+badge(t.enabled?'passed':'failed',t.enabled?'시연 연결됨':'미연결')+'<p>'+esc(t.purpose)+'</p><strong>입력</strong><p>'+esc(mappingNames[t.input])+'</p><strong>성공 기준</strong><p>'+esc(t.success)+'</p><small>등록한 도구는 프로세스·태스크·잡에서 연결할 수 있습니다.</small></div>'}else{const s=draft.sites[siteId];title='현장별 절차 적용';html='<div class="m-preview-card"><h2>'+esc(s.country+' · '+s.name)+'</h2><div class="m-site-summary"><div class="m-site-line"><span>인프라</span><strong>'+(s.reuse?'재사용 상태 확인':'신규 준비 상태 확인')+'</strong></div><div class="m-site-line"><span>인터페이스 검증</span><strong>'+(s.interface?'포함':'연계 미사용으로 제외')+'</strong></div><div class="m-site-line"><span>시간대</span><strong>'+esc(s.zone)+'</strong></div></div><p>이 조건은 게시 후 새 셋업에 반영됩니다.</p></div>'}setText('m-preview-title',title);q('#m-preview-content').innerHTML=html;icons()}
function touch(){const hadTest=testedRevision>=0;revision++;testedRevision=-1;if(hadTest)designStatus('시험 이후 수정되었습니다. 다시 시험한 뒤 게시해 주세요.',true);previewMode='live';setText('m-draft-version','v1.'+(version+1)+' 초안 · 저장 전 변경 있음');renderPreview();renderNav()}
function designStatus(text,failed=false){q('#m-design-status').hidden=false;q('#m-design-status').textContent=text;q('#m-design-status').classList.toggle('failure',failed)}
function changes(){const out=[];for(const[k,label]of[['nodes','업무'],['skills','스킬·지침'],['tools','도구'],['sites','현장']]){let count=0;for(const[id,obj]of Object.entries(draft[k]))if(JSON.stringify(obj)!==JSON.stringify(published[k][id]))count++;if(count)out.push(label+' '+count+'개 추가·변경')}if(JSON.stringify(draft.roots)!==JSON.stringify(published.roots))out.push('프로세스 순서·구성 변경');return out.length?out:['변경 없음']}
function dryChecks(ids,failIndex=-1){let stopped=false;return ids.map((id,i)=>{if(stopped)return'skipped';if(!draft.tools[id]?.enabled||draft.tools[id]?.mockResult==='failure'||i===failIndex){stopped=true;return'failed'}return'passed'})}
function validate() {
  const structure = [], binding = [], skillErrors = [], sites = [];
  const active = Object.values(draft.nodes).filter(n => ancestry(draft.nodes,n.id).every(p=>p.enabled!==false));
  for (const n of active) {
    if (!n.name.trim() || !n.rule.trim()) structure.push(n.name+': 이름·완료 기준 필요');
    if (n.type !== 'j' && !n.children.some(id=>draft.nodes[id]?.enabled!==false)) structure.push(n.name+': 사용 가능한 하위 작업 필요');
    if (n.deps.some(id=>!draft.nodes[id] || draft.nodes[id].type!==n.type)) structure.push(n.name+': 선행 참조 오류');
    if (n.type === 'j' && n.mode === 'tool' && !n.tools.length) binding.push(n.name+': 실행 도구 필요');
    for (const id of n.tools) {
      const tool = draft.tools[id], input = n.bindings[id] || tool?.input;
      if (!tool?.enabled) binding.push(n.name+': '+(tool?.name||id)+' 미연결');
      if (!mappingNames[input] || input !== tool?.input) binding.push(n.name+': 도구에 맞는 입력값 종류 확인 필요');
      if (!tool?.name.trim() || !tool?.purpose.trim() || !tool?.success.trim()) binding.push(n.name+': 도구 이름·설명·성공 기준 필요');
      for (const parent of ancestry(draft.nodes,n.id).slice(0,-1)) {
        if (parent.tools.length && !parent.tools.includes(id)) binding.push(n.name+': 상위 허용 도구 확인 필요');
      }
    }
    for (const id of n.skills) if (!draft.skills[id]?.name.trim() || !draft.skills[id]?.body.trim()) skillErrors.push(n.name+': 스킬 이름·내용 필요');
  }
  if (!draft.skills.common?.locked || !draft.skills.common.body.trim()) skillErrors.push('공통 실행 지침 필요');
  // Expand inherited process/task prerequisites to leaf jobs before detecting cycles.
  const visiting = new Set(), visited = new Set();
  function walk(id) {
    if (visiting.has(id)) { structure.push('선행 작업 순환 참조'); return; }
    if (visited.has(id) || !draft.nodes[id]) return;
    visiting.add(id);
    dependencies(draft.nodes,id).flatMap(dep=>leaves(draft.nodes,dep)).forEach(walk);
    visiting.delete(id); visited.add(id);
  }
  active.filter(n=>n.type==='j').forEach(n=>walk(n.id));
  for (const site of Object.values(draft.sites)) {
    if (['country','name','line','zone','db','ap'].some(key=>!String(site[key]||'').trim())) sites.push(site.name+': 현장 필수 정보 필요');
  }
  const jobs = active.filter(n=>n.type==='j'&&n.mode==='tool');
  const normal = jobs.every(n=>dryChecks(n.tools).every(status=>status==='passed'));
  const multiple = jobs.find(n=>n.tools.length>1);
  const fail = multiple ? dryChecks(multiple.tools,0) : ['failed','skipped'];
  testResults = [
    {name:'프로세스·태스크·잡 구조',pass:!structure.length,detail:structure[0]||'하위 작업과 상속된 선행 참조 확인'},
    {name:'도구·입력 연결',pass:!binding.length,detail:binding[0]||'등록된 도구와 현장 입력 연결 확인'},
    {name:'스킬·공통 지침',pass:!skillErrors.length,detail:skillErrors[0]||'공통 지침 유지 및 연결 자산 확인'},
    {name:'현장 정보',pass:!sites.length,detail:sites[0]||'국가·공장·라인·진단 경로 이름 확인'},
    {name:'정상 응답 시뮬레이션',pass:normal,detail:normal?'연결된 점검의 모의 성공 응답 확인':'실패로 설정한 모의 응답 또는 미연결 도구 확인'},
    {name:'실패 전파 시뮬레이션',pass:fail[0]==='failed'&&fail.slice(1).every(status=>status==='skipped'),detail:'필수 점검 실패 후 의존 점검은 미수행'}
  ];
  testedRevision = testResults.every(t=>t.pass) ? revision : -1;
  previewMode = 'test'; renderPreview();
  designStatus(testedRevision===revision?'시험을 통과한 예시입니다. 초안을 저장하고 변경 내용을 확인한 뒤 게시할 수 있어요.':'수정이 필요한 항목을 확인해 주세요.',testedRevision!==revision);
}

function publish(){if(savedRevision!==revision||testedRevision!==revision||!testResults.every(x=>x.pass)){designStatus('현재 변경 내용으로 시험 실행을 먼저 진행해 주세요.',true);return}if(changes()[0]==='변경 없음'){designStatus('게시할 변경 내용이 없습니다.');return}published=clone(draft);version++;draft=clone(published);revision=0;savedRevision=0;testedRevision=-1;previewMode='published';setText('m-draft-version','v1.'+(version+1)+' 초안');renderPreview();designStatus('v1.'+version+'을 게시한 시뮬레이션입니다. 실제 서버·공용 설정은 변경하지 않았습니다.')}
function addNode(type,parent){const id='new-'+(++newCounter);draft.nodes[id]={id,type,name:type==='p'?'새 프로세스':type==='t'?'새 태스크':'새 잡',parent,children:[],description:'',condition:'all',mode:'manual',tools:[],skills:[],bindings:{},deps:[],rule:'필수 확인 완료',enabled:true};if(parent){draft.nodes[parent].children.push(id);expanded.add(parent)}else{const cat=ancestry(draft.nodes,editId)[0]?.category||'setup';draft.nodes[id].category=cat;draft.roots[cat].push(id)}editId=id;touch();renderDesigner()}
function moveNode(delta){const n=draft.nodes[editId];const a=n.parent?draft.nodes[n.parent].children:draft.roots[n.category],i=a.indexOf(editId),j=i+delta;if(j<0||j>=a.length)return;[a[i],a[j]]=[a[j],a[i]];touch();renderDesigner()}
function addAsset(kind){const id='asset-'+(++newCounter);if(kind==='skill'){draft.skills[id]={id,name:'새 스킬',type:'skill',body:'',locked:false};assetId=id}else if(kind==='tool'){draft.tools[id]={id,name:'새 점검 도구',purpose:'',type:'진단 API',input:'site',success:'기대 응답 일치',mockResult:'success',enabled:false};toolId=id}else{draft.sites[id]={id,country:'미국',name:'새 공장',line:'대상 라인',zone:'확인 필요',reuse:false,interface:false,db:'진단 경로 확인 필요',ap:'진단 경로 확인 필요'};siteId=id}touch();renderDesigner()}
function showSummary(){const cs=c(),r=ancestry(cs.snapshot.nodes,selected)[0].id,[d,t]=count(cs,r);q('#m-work-content').innerHTML='<div class="m-document"><small>검증 결과 요약 · 예시</small><h2>'+esc(cs.snapshot.nodes[r].name)+'</h2><p>'+esc(cs.system+' · '+cs.site.country+' '+cs.site.name+' · '+cs.site.line)+'</p><strong>필수 잡 '+d+' / '+t+' 완료</strong>'+leaves(cs.snapshot.nodes,r).map(id=>'<div class="summary-line"><button class="material-button" data-node="'+id+'">'+esc(cs.snapshot.nodes[id].name)+'</button>'+badge(state(cs,id))+'</div>').join('')+'<small>절차 v1.'+cs.version+' · 현장 조건과 실행 결과를 함께 기록한 예시입니다.</small><button data-node="'+r+'">전체 업무로 돌아가기</button></div>';icons()}
async function send(text) {
  const request=text.trim();
  if(!request)return;
  const cs=c();append('user',request);
  const nodes=Object.values(cs.snapshot.nodes).filter(n=>ancestry(cs.snapshot.nodes,n.id)[0].category===category);
  const n=nodes.sort((a,b)=>b.name.length-a.name.length).find(node=>request.includes(node.name));
  const help=()=>append('assistant','이 목업은 정해진 시연 문구만 처리합니다. “DB 연결 확인 실행해줘”, “AP 연결 확인 재시도해줘”, “전체 진행 상황 보여줘”, “설계 워크스페이스 열어줘”를 사용할 수 있어요. 실제 업무 API는 연결하지 않습니다.');
  if(/하지\s*마|하지\s*말|말아|취소|삭제|Jira|Confluence|GitHub|SQL|실제\s*(API|DB)/i.test(request)){help();return;}
  if(/^설계\s*워크스페이스(?:를)?\s*(열어줘|열어주세요|보여줘|열기)?[.!?]?$/.test(request)) {
    return action('mode',{mode:'design'});
  }
  if(/^(전체|현재)\s*(진행\s*상황|업무)(?:을|를)?\s*(보여줘|알려줘|보여주세요)?[.!?]?$/.test(request)) {
    action('select-node',{id:ancestry(cs.snapshot.nodes,selected)[0].id});
    const[done,total]=count(cs,selected);
    append('assistant','현재 필수 잡 '+total+'개 중 '+done+'개가 완료된 예시입니다. 실패·미수행 항목과 다음 행동을 오른쪽에서 확인할 수 있어요.');return;
  }
  if(/^다음\s*(작업|할\s*일)(?:을|를)?\s*(보여줘|알려줘|보여주세요)?[.!?]?$/.test(request)) {
    const next=nextJob(cs,selected);
    if(next){action('select-node',{id:next});append('assistant',cs.snapshot.nodes[next].name+'를 열었어요.');}
    else append('assistant','선택한 범위의 필수 작업이 모두 완료됐어요.');return;
  }
  // Only a known task name or an exact current-task command can run a simulation.
  const runSuffix=/^(?:을|를)?\s*(?:점검\s*)?(실행|재시도)(해줘|해주세요|하기)?[.!?]?$/;
  const command=n?request.replace(n.name,'').trim():request;
  if(runSuffix.test(command)) {
    if(n)action('select-node',{id:n.id});
    await action('run');return;
  }
  if(/^(?:결과\s*)?(요약|보고서)(?:을|를)?\s*(보여줘|만들어줘|보기)?[.!?]?$/.test(request)) {
    action('summary');append('assistant','확인된 실행 결과로 요약을 만든 예시입니다.');return;
  }
  if(/^(왜|원인)(?:을)?\s*(알려줘|보여줘)?[.!?]?$/.test(request)) {
    const fail=jobState(cs,selected).checks.find(check=>check.status==='failed');
    append('assistant',fail?'확인된 실패는 '+fail.detail+'입니다. 이 예시만으로 근본 원인을 확정하지 않습니다.':'현재 선택한 업무의 확인 결과를 오른쪽에서 볼 수 있어요.');return;
  }
  if(n&&/^(?:을|를)?\s*(보여줘|열어줘|열기|보기)?[.!?]?$/.test(command)) {
    action('select-node',{id:n.id});append('assistant',n.name+'를 오른쪽에 열었어요.');return;
  }
  help();
}

async function action(name, payload = {}) {
  if(name==='reset') return init();
  if(name==='select-node') return choose(payload.id);
  if(name==='mode') return changeMode(payload.mode);
  if(name==='category') {mode='run';return switchCategory(payload.category);}
  if(name==='section') {section=payload.section;previewMode='live';return renderAll();}
  if(name==='edit-node') {if(!draft.nodes[payload.id])return;editId=payload.id;previewMode='live';renderNav();return renderDesigner();}
  if(name==='expand') {expanded.has(payload.id)?expanded.delete(payload.id):expanded.add(payload.id);return renderNav();}
  if(name==='show-nav') {navCollapsed=false;navOpen=true;return renderNav();}
  if(name==='hide-nav') {navOpen=false;return renderNav();}
  if(name==='toggle-nav') {navCollapsed=!navCollapsed;return renderNav();}
  if(name==='pin') {pinned=!pinned;navOpen=true;return renderNav();}
  if(name==='case') {if(!cases[payload.id])return;caseId=payload.id;category=c().category;selected=c().selected;newCase=false;return renderAll();}
  if(name==='new-case') {newCase=true;return renderWork();}
  if(name==='chat') return send(String(payload.text||''));
  if(name==='save-draft') {savedRevision=revision;setText('m-draft-version','v1.'+(version+1)+' 초안 · 저장됨');return designStatus('이 목업 세션 안에 초안을 저장했습니다. 새로고침하면 초기화됩니다.');}
  if(name==='test-draft') return validate();
  if(name==='review-publish') {
    if(savedRevision!==revision){designStatus('현재 변경 내용을 초안 저장한 뒤 게시해 주세요.',true);return;}
    if(testedRevision!==revision){designStatus('마지막 변경 내용으로 시험 실행을 먼저 진행해 주세요.',true);return;}
    if(changes()[0]==='변경 없음'){designStatus('게시할 변경 내용이 없습니다.');return;}
    previewMode='publish';return renderPreview();
  }
  if(name==='tool-remove') {const n=draft.nodes[editId],id=n.tools.splice(payload.index,1)[0];delete n.bindings[id];touch();return renderDesigner();}
  if(name==='tool-up') {const a=draft.nodes[editId].tools,i=payload.index;if(i>0&&i<a.length){[a[i],a[i-1]]=[a[i-1],a[i]];touch();renderDesigner();}return;}
  if(name==='update-field') return updateField(payload);
  if(name==='select-asset') {assetId=payload.id;previewMode='live';return renderDesigner();}
  if(name==='select-tool') {toolId=payload.id;previewMode='live';return renderDesigner();}
  if(name==='select-site') {siteId=payload.id;previewMode='live';return renderDesigner();}
  if(name==='preview-site') {siteId=payload.id;return renderPreview();}
  if(name==='bind-skill'||name==='bind-dependency') {
    const n=draft.nodes[editId],key=name==='bind-skill'?'skills':'deps';
    n[key]=payload.checked?[...new Set([...n[key],payload.id])]:n[key].filter(id=>id!==payload.id);return touch();
  }
  if(name==='map-input') {draft.nodes[editId].bindings[payload.id]=payload.value;return touch();}

if(name==='generate-draft')return generateDraft();if(name==='run')return runJob();if(name==='manual')return manual();if(name==='summary')return showSummary();if(name==='cancel-case'){newCase=false;return renderWork()}if(name==='create-case'){const target=q('#m-start-site').value||Object.keys(published.sites)[0],sys=q('#m-start-system').value||'EMS';caseId=makeCase('setup',target,false,sys);category='setup';selected=c().selected;newCase=false;expanded.add(selected);renderAll();append('assistant','새 셋업을 v1.'+version+'과 선택한 현장 조건으로 시작한 예시입니다. 기존 셋업의 상태는 따로 유지됩니다.');return}if(name==='new-case-after-publish'){mode='run';newCase=true;renderAll();return}if(name==='preview-live'){previewMode='live';renderPreview();return}if(name==='confirm-publish')return publish();if(name==='new-process')return addNode('p',null);if(name==='add-child'){const n=draft.nodes[editId];if(n.type!=='j')addNode(n.type==='p'?'t':'j',editId);return}if(name==='move-up')return moveNode(-1);if(name==='move-down')return moveNode(1);if(name==='new-skill')return addAsset('skill');if(name==='new-tool')return addAsset('tool');if(name==='new-site')return addAsset('site');if(name==='skill-draft'){const a=draft.skills[assetId];if(a.locked)return;a.body='목표: '+a.name+'\n1. 현재 업무 대상과 입력 자료를 확인합니다.\n2. 연결된 점검을 선행 조건에 따라 수행합니다.\n3. 성공·실패·미수행 결과와 근거를 구분합니다.\n4. 필요한 담당자 확인 후 완료를 기록합니다.';touch();renderDesigner();designStatus('작성 예시입니다. 내용을 검토한 뒤 업무에 연결해 주세요.');return}if(name==='test-tool'){const t=draft.tools[toolId];const ok=t.enabled&&t.mockResult!=='failure';designStatus(ok?'예시 응답 시험 통과: '+t.name+' · '+t.success:(t.enabled?'등록된 모의 실패 응답입니다.':'실행하지 못했습니다. 시연 어댑터가 연결되지 않았습니다.'),!ok);return}if(name==='add-tool-binding'){const id=q('#m-tool-to-add').value;if(!id){designStatus('연결할 도구를 선택해 주세요.',true);return}const n=draft.nodes[editId];if(!n.tools.includes(id)){n.tools.push(id);n.bindings[id]=draft.tools[id].input;touch();renderDesigner()}return}}
root.addEventListener('click', event => {
  const link=event.target.closest('a.m-return');
  if(link && window.parent!==window) {
    event.preventDefault();window.parent.postMessage({type:'ees-work-demo-close'},window.location.origin);return;
  }
  const button=event.target.closest('button');
  if(!button || button.disabled)return;
  const data=button.dataset;
  if(data.mode)return action('mode',{mode:data.mode});
  if(data.category)return action('category',{category:data.category});
  if(data.section)return action('section',{section:data.section});
  if(data.node)return action('select-node',{id:data.node});
  if(data.editNode)return action('edit-node',{id:data.editNode});
  if(data.expand)return action('expand',{id:data.expand});
  if(data.showNav)return action('show-nav');
  if(data.prompt)return action('chat',{text:data.prompt});
  if(data.action)return action(data.action);
  if(data.toolRemove!==undefined)return action('tool-remove',{index:+data.toolRemove});
  if(data.toolUp!==undefined)return action('tool-up',{index:+data.toolUp});
});
function updateField({kind,field,value}) {
  const id=kind==='node'?editId:kind==='skill'?assetId:kind==='tool'?toolId:siteId;
  const group=kind==='node'?draft.nodes:kind==='skill'?draft.skills:kind==='tool'?draft.tools:kind==='site'?draft.sites:null;
  const obj=group?.[id];
  const allowed={node:['name','description','condition','enabled','mode','rule'],skill:['name','type','body'],tool:['name','purpose','type','input','success','enabled','mockResult'],site:['country','name','line','zone','reuse','interface','db','ap']};
  if(!obj||obj.locked||!allowed[kind]?.includes(field))return;
  obj[field]=value;touch();
}
function fieldPayload(el){return {kind:el.dataset.kind,field:el.dataset.field,value:el.type==='checkbox'?el.checked:el.value};}
root.addEventListener('input',event=>{
  const el=event.target;
  if(el.dataset.field&&el.tagName!=='SELECT'&&el.type!=='checkbox')action('update-field',fieldPayload(el));
});
root.addEventListener('change',event=>{
  const el=event.target;
  if(el.id==='m-start-site'||el.id==='m-start-system'){updateSitePlan();return;}
  if(el.dataset.selectAsset)return action('select-asset',{id:el.value});
  if(el.dataset.selectTool)return action('select-tool',{id:el.value});
  if(el.dataset.selectSite)return action('select-site',{id:el.value});
  if(el.dataset.previewSite)return action('preview-site',{id:el.value});
  if(el.dataset.field){action('update-field',fieldPayload(el));if(el.dataset.field==='mode')renderDesigner();return;}
  if(el.dataset.bindSkill)return action('bind-skill',{id:el.dataset.bindSkill,checked:el.checked});
  if(el.dataset.bindDep)return action('bind-dependency',{id:el.dataset.bindDep,checked:el.checked});
  if(el.dataset.mapInput)return action('map-input',{id:el.dataset.mapInput,value:el.value});
});
q('#m-case').onchange=()=>action('case',{id:q('#m-case').value});
q('#m-pin').onclick=()=>action('pin');
q('#m-toggle-nav').onclick=()=>action('toggle-nav');
q('#m-edit-from-run').onclick=()=>action('mode',{mode:'design'});
q('#m-new-case').onclick=()=>action('new-case');
q('#m-reset').onclick=()=>action('reset');
q('#m-chat').onsubmit=event=>{event.preventDefault();const text=q('#m-input').value.trim();if(!text)return;q('#m-input').value='';return action('chat',{text});};
q('#m-save-draft').onclick=()=>action('save-draft');
q('#m-test-draft').onclick=()=>action('test-draft');
q('#m-review-publish').onclick=()=>action('review-publish');
root.addEventListener('keydown',event=>{if(event.key==='Escape'&&!pinned&&mode==='run')action('hide-nav');});
// A clone is returned so inspection cannot mutate the running simulation.
window.EESWorkDemo=Object.freeze({
  dispatch:action,
  snapshot:()=>clone({version,revision,testedRevision,savedRevision,mode,section,category,selected,editId,caseId,cases,messages,draft,published})
});
init();
})();
