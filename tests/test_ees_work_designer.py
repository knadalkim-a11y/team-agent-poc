"""Production Workspace editor at synthetic DOM boundaries; not browser E2E."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
NODE_DESIGNER = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const input=JSON.parse(fs.readFileSync(0,'utf8')), copy=x=>JSON.parse(JSON.stringify(x));
let form=null,markup='',mutations=[];
const status={textContent:''};
// FormData includes fields inside closed details, and omits disabled controls.
function parseForm(html) {
  const values=new Map(), add=(k,v)=>values.set(k,[...(values.get(k)||[]),v]);
  for(const match of html.matchAll(/<input\b([^>]*)>/g)){
    const a=match[1],name=a.match(/name="([^"]*)"/)?.[1];
    if(!name||/\bdisabled\b/.test(a)||(/type="checkbox"/.test(a)&&!a.includes('checked')))continue;
    add(name,a.match(/value="([^"]*)"/)?.[1]||'on');
  }
  for(const match of html.matchAll(/<textarea\b[^>]*name="([^"]*)"[^>]*>([\s\S]*?)<\/textarea>/g))add(match[1],match[2]);
  for(const match of html.matchAll(/<select\b[^>]*name="([^"]*)"[^>]*>([\s\S]*?)<\/select>/g)){
    const options=[...match[2].matchAll(/<option\b([^>]*)>/g)];
    const a=(options.find(x=>x[1].includes('selected'))||options[0])?.[1];
    if(a)add(match[1],a.match(/value="([^"]*)"/)?.[1]||'');
  }
  return {values};
}
const section={dataset:{},querySelectorAll:selector=>selector==='button[data-mutation]'?mutations:[],remove(){},
  set innerHTML(v){markup=v;form=parseForm(v);status.textContent=v.match(/class="ew-designer-status"[^>]*>([^<]*)</)?.[1]||'';
    mutations=[...v.matchAll(/<button\b([^>]*data-mutation[^>]*)>/g)].map(match=>({dataset:{action:match[1].match(/data-action="([^"]*)"/)?.[1]},disabled:match[1].includes('disabled')}));},get innerHTML(){return markup;}};
const container={children:[],parentElement:{querySelector:()=>null},append(n){n.parentElement=this;}};
const context={document:{createElement:()=>section},location:{},confirm:()=>true,
  FormData:class{constructor(f){this.values=f.values;}has(k){return this.values.has(k);}get(k){return this.values.get(k)?.[0];}getAll(k){return this.values.get(k)||[];}}};
vm.createContext(context);
vm.runInContext(fs.readFileSync(input.view,'utf8')+'\n'+fs.readFileSync(input.source,'utf8'),context);
context.document.querySelector=selector=>selector==='#workspace-container'?container:selector==='#ees-work-node-form'?form:selector==='#ees-work-designer .ew-designer-status'?status:null;
const definition={version:1,systems:['EMS'],sites:{f:{id:'f',name:'F',country:'K'}},roots:{setup:['p'],ops:[],incident:[]},
  skills:{common:{id:'common',name:'정책',locked:true},s:{id:'s',name:'참조 스킬'}},
  tools:{tool:{id:'tool',name:'참조 도구',input:'db',adapter:'unavailable'}},nodes:{
    p:{id:'p',type:'p',category:'setup',name:'업무',children:['t'],skills:[],tools:[]},
    t:{id:'t',type:'t',parent:'p',category:'setup',name:'하위',children:['a','b'],skills:[],tools:[]},
    a:{id:'a',type:'j',parent:'t',category:'setup',name:'원본',condition:'all',enabled:true,mode:'tool',
       children:[],skills:['common','s'],deps:['b'],systems:['EMS'],tools:['tool'],bindings:{tool:'db'},instructions:'안내',rule:'조건'},
    b:{id:'b',type:'j',parent:'t',category:'setup',name:'선행',condition:'all',enabled:true,mode:'manual',
       children:[],skills:[],deps:[],systems:['EMS'],tools:[],bindings:{}}}};
if(input.scenario==='large_children')for(let i=0;i<43;i++){
  const id='bulk-'+i;definition.nodes[id]={...copy(definition.nodes.b),id,name:'검사 '+String(i).padStart(2,'0'),mode:i%2?'manual':'tool'};
  definition.nodes.t.children.push(id);
}
if(input.scenario==='absent_references'){
  definition.nodes.a.skills.push('personal-private');definition.nodes.a.tools.push('personal-tool');
  definition.nodes.a.bindings['personal-tool']='original-target';definition.nodes.a.systems.push('private-system');
}
if(input.scenario==='adapter_states'){
  for(const [id,settings] of Object.entries({simulated:{adapter:'mock'},missing:{},disabled:{adapter:'mock',enabled:false},native:{adapter:'mock',source:'open_webui'}})){
    definition.tools[id]={id,name:id,input:'db',...settings};definition.nodes.a.tools.push(id);definition.nodes.a.bindings[id]='db';
  }
}
const state={catalog:definition,draft:copy(definition),draft_revision:1,can_manage:true};
const designer=vm.runInContext('createWorkDesigner({callbacks:{}})',context);
const snap=()=>({state,category:'setup',adminRoute:true,errorMessage:'',busy:false});
designer.acceptServer(state);designer.render(snap());
const click=id=>designer.handleEvent({type:'click',target:{closest:s=>s==='#ees-work-designer'?section:{dataset:{action:'edit_node',nodeId:id}}}});
const action=(action,dataset={})=>designer.handleEvent({type:'click',target:{closest:s=>s==='#ees-work-designer'?section:{dataset:{action,...dataset}}}});
const control=(id,value,type='input')=>designer.handleEvent({type,target:{id,value,closest:s=>s==='#ees-work-designer'?section:null}});
click('a');
const event=type=>designer.handleEvent({type,target:{closest:s=>s==='#ees-work-designer'?section:null}});
function change(name,value,type='input'){if(Array.isArray(value)&&!value.length)form.values.delete(name);else form.values.set(name,Array.isArray(value)?value:[value]);event(type);}
if(input.scenario==='refresh'){
  const clean=designer.readDraft();designer.markSaved(clean.definition,clean.revision);designer.render(snap());
  assert.doesNotMatch(status.textContent,/저장하지 않은 변경/);
  change('instructions','저장 전 새 안내');
  assert.match(status.textContent,/저장하지 않은 변경/, 'Typing must show the unsaved state without rerendering the form');
  designer.acceptServer(copy(state));designer.render(snap());
  assert.match(markup,/저장 전 새 안내/);assert.equal(designer.readDraft().dirty,true);
}else if(input.scenario==='selection'){
  change('instructions','접힌 설정 유지');click('b');click('a');
  const draft=designer.readDraft().definition.nodes.a;
  assert.equal(draft.instructions,'접힌 설정 유지');
  assert.deepEqual(copy(draft.skills),['common','s']);assert.deepEqual(copy(draft.deps),['b']);
  assert.deepEqual(copy(draft.systems),['EMS']);assert.deepEqual(copy(draft.bindings),{tool:'db'});
}else if(input.scenario==='save_race'){
  change('instructions','저장 요청');const submitted=designer.readDraft();
  change('instructions','요청 뒤 계속 입력');designer.markSaved(submitted.definition,2);
  designer.acceptServer({...copy(state),draft:submitted.definition,draft_revision:2});designer.render(snap());
  const draft=designer.readDraft();assert.equal(draft.dirty,true);assert.equal(draft.revision,2);
  assert.equal(draft.definition.nodes.a.instructions,'요청 뒤 계속 입력');
}else if(input.scenario==='change'){
  change('enabled',[],'change');designer.acceptServer(copy(state));designer.render(snap());
  assert.equal(designer.readDraft().definition.nodes.a.enabled,false);
}else if(input.scenario==='large_children'){
  click('t');
  assert.match(markup,/전체 45개 · 검색 결과 45개/);
  assert.equal((markup.match(/class="ew-editor-child"/g)||[]).length,20);
  change('instructions','작업 탐색 중 입력');action('child_page',{page:'2'});
  assert.match(markup,/41–45 표시/);assert.equal((markup.match(/class="ew-editor-child"/g)||[]).length,5);
  control('ees-work-child-search','검사 0');
  assert.match(markup,/전체 45개 · 검색 결과 10개 · 1–10 표시/);
  control('ees-work-child-mode','tool','change');
  assert.match(markup,/검색 결과 5개/);assert.equal((markup.match(/class="ew-editor-child"/g)||[]).length,5);
  click('bulk-0');click('t');
  assert.match(markup,/검색 결과 5개/);assert.match(markup,/value="검사 0"/);
  assert.equal(designer.readDraft().definition.nodes.t.instructions,'작업 탐색 중 입력');
  assert.equal(Object.keys(designer.readDraft().definition.nodes).length,47);
}else if(input.scenario==='absent_references'){
  change('instructions','기존 자산 보존');click('b');click('a');
  const node=designer.readDraft().definition.nodes.a;
  assert.deepEqual(copy(node.skills),['common','s','personal-private']);
  assert.deepEqual(copy(node.tools),['tool','personal-tool']);
  assert.deepEqual(copy(node.bindings),{tool:'db','personal-tool':'original-target'});
  assert.deepEqual(copy(node.systems),['EMS','private-system']);
}else if(input.scenario==='hierarchy'){
  click('p');action('add_child');let draft=designer.readDraft().definition;
  const addedStage=draft.nodes.p.children.at(-1);assert.equal(draft.nodes[addedStage].type,'t');
  assert.equal(draft.nodes[addedStage].name,'새 단계');
  change('name','베타 단계');action('add_child');draft=designer.readDraft().definition;
  const job=draft.nodes[addedStage].children[0];assert.equal(draft.nodes[job].name,'새 작업');
  assert.equal(draft.nodes[addedStage].name,'베타 단계');
  click(addedStage);action('move_up');assert.equal(designer.readDraft().definition.nodes.p.children[0],addedStage);
  action('delete_node');draft=designer.readDraft().definition;
  assert.equal(draft.nodes[addedStage],undefined);assert.equal(draft.nodes[job],undefined);
  assert.deepEqual(copy(draft.nodes.p.children),['t']);assert.equal(draft.nodes.a.name,'원본');
}else if(input.scenario==='publish_gate'){
  const publish=()=>mutations.find(button=>button.dataset.action==='publish');
  assert.equal(publish().disabled,true);
  const clean=designer.readDraft();designer.markSaved(clean.definition,1);
  state.draft=clean.definition;state.validated_revision=1;designer.acceptServer(copy(state));designer.render(snap());
  assert.equal(publish().disabled,false);
  change('instructions','확인 이후 변경');assert.equal(publish().disabled,true);
}else if(input.scenario==='adapter_states'){
  assert.equal((markup.match(/합성 시연 점검/g)||[]).length,1,'Only an enabled built-in mock is executable');
  assert.equal((markup.match(/<small class="ew-muted">실행 연결 필요<\/small>/g)||[]).length,4);
  action('editor_tab',{tab:'tools'});
  assert.equal((markup.match(/<p class="ew-muted">합성 시연 점검<\/p>/g)||[]).length,1);
  assert.equal((markup.match(/<p class="ew-muted">실행 연결 필요<\/p>/g)||[]).length,4);
}
process.stdout.write('ok\n');
'''


@unittest.skipUnless(shutil.which('node'), 'Node is required for Workspace contracts.')
class WorkDesignerTests(unittest.TestCase):
    def check(self, scenario):
        result = subprocess.run([shutil.which('node'), '-e', NODE_DESIGNER],
            input=json.dumps({'source': str(ROOT / 'branding/ees/ui/ees-work-designer.js'),
                              'view': str(ROOT / 'branding/ees/ui/ees-work-view.js'), 'scenario': scenario}),
            capture_output=True, encoding='utf-8', timeout=10, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'ok')

    def test_unsaved_typing_survives_server_refresh_and_rerender(self):
        self.check('refresh')

    def test_folded_settings_references_and_policy_survive_selection(self):
        self.check('selection')

    def test_typing_during_save_keeps_new_text_and_acknowledged_revision(self):
        self.check('save_race')

    def test_change_event_is_captured_before_server_refresh(self):
        self.check('change')

    def test_large_stage_search_filter_and_pages_preserve_unsaved_edit(self):
        self.check('large_children')

    def test_inaccessible_references_and_existing_bindings_survive_editing(self):
        self.check('absent_references')

    def test_stage_and_job_creation_reordering_and_removal_keep_existing_nodes(self):
        self.check('hierarchy')

    def test_publish_requires_checked_saved_draft_and_relocks_after_typing(self):
        self.check('publish_gate')

    def test_missing_disabled_and_native_adapters_never_appear_executable(self):
        self.check('adapter_states')
