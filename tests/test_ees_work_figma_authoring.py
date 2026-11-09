"""B2-1 authoring command/state regressions using the shared synthetic DOM.

Reconstructed from this session's retained source/patch text after workspace
loss. This is newly verified test source, not a recovered byte-identical file.
Native rendering and real SQLite round trips are checked separately.
"""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
PRELUDE = (ROOT / 'tests/test_ees_work_authoring_ui.cjs').read_text(encoding='utf-8').split('\ntest(', 1)[0]


@unittest.skipUnless(shutil.which('node'), 'Node is required for authoring contracts.')
class FigmaAuthoringScheduleTests(unittest.TestCase):
    def run_contract(self, script):
        result = subprocess.run([shutil.which('node'), '-e', PRELUDE + '\n' + script],
                                cwd=ROOT / 'tests', capture_output=True, encoding='utf-8',
                                timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    # 2026-11-02 user decision: the execution-mode tab and schedule authoring are
    # removed. Saved modes/schedules remain data, start inputs move to the content
    # tab, and reservations made earlier can only be listed and stopped.
    def test_no_run_mode_tab_keeps_saved_mode_and_schedule_through_editing_and_save(self):
        self.run_contract(r"""
(async()=>{
const h=harness(),record=h.workflows.get('w');
const schedule={frequency:'weekly',interval:2,weekday:1,anchor:'2026-10-06T09:00',timezone:'Asia/Seoul',name_template:'{date} 회차',stage_deadlines:{t:{offset_days:-8,end_offset_days:-6}},opening:'on_schedule',closing:'after_last_stage',non_working_days:'notify_no_shift'};
record.draft.mode='periodic';record.draft.schedule=copy(schedule);h.render();const original=copy(h.draft().definition);
assert.doesNotMatch(h.markup,/실행 방식|data-tab="schedule"|data-author-action="run_mode"|data-author-action="schedule_tools"|일정 미리보기·서버 예약/);
for(const tab of ['content','rules','history'])assert.match(h.markup,new RegExp('data-tab="'+tab+'"'));
h.click('tab',{tab:'schedule'});await flush();
assert.match(h.markup,/data-author-tab="content"/);assert.match(h.markup,/시작할 때 받는 값/);assert.match(h.markup,/단계와 작업/);
assert.deepEqual(h.draft().definition,original);assert.equal(h.draft().dirty,false);assert.equal(h.forms['ew-author-schedule'],undefined);
h.click('run_mode',{id:'emergency'});h.click('schedule_tools');await flush();assert.equal(h.draft().definition.mode,'periodic');assert.equal(h.draft().dirty,false);
h.dialogs.push({id:'release_date',name:'배포일',type:'datetime',scope:'run',required:true,options_source:'manual',options:''});
h.click('start_input_add');await flush();assert.equal(h.draft().definition.nodes.p.inputs.at(-1).id,'release_date');
h.click('save');await flush();
assert.equal(h.writes[0].action,'save_draft');assert.equal(h.writes[0].expected_revision,1);
assert.equal(h.writes[0].definition.mode,'periodic');assert.deepEqual(h.writes[0].definition.schedule,schedule);
await h.open('q');await h.open('w');assert.deepEqual(h.draft().definition.schedule,schedule);assert.equal(h.operations.length,0);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")

    def test_saved_periodic_draft_renders_no_schedule_fields_or_schedule_queries(self):
        self.run_contract(r"""
(async()=>{
const h=harness(),record=h.workflows.get('w');record.draft.mode='periodic';record.draft.schedule={timezone:'Asia/Seoul',anchor:'2026-10-06T09:00',frequency:'weekly',interval:2};h.render();
for(const tab of ['content','rules','history']){h.click('tab',{tab});await flush();
  assert.doesNotMatch(h.markup,/name="anchor"|name="frequency"|name="name_template"|data-author-action="schedule_preview"|data-author-action="schedule_create"|단계 기한|회차 열기와 닫기/);}
h.click('schedule_preview');h.click('schedule_create');await flush();
assert.equal(h.operations.length,0);assert.equal(h.writes.length,0);assert.equal(h.draft().dirty,false);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")

    def test_start_inputs_are_edited_below_stages_in_the_content_tab(self):
        self.run_contract(r"""
(async()=>{
const h=harness();await flush();
const at=label=>h.markup.indexOf(label);assert.ok(at('시작할 때 받는 값')>=0);assert.ok(at('단계와 작업')>=0);assert.ok(at('시작할 때 받는 값')>at('단계와 작업'));
h.dialogs.push({id:'incident_at',name:'발생 시각',type:'datetime',scope:'run',required:true,options_source:'manual',options:''});
h.click('start_input_add');await flush();
assert.equal(h.draft().definition.nodes.p.inputs[0].id,'incident_at');assert.equal(h.draft().definition.nodes.p.inputs[0].scope,'run');assert.equal(h.draft().definition.nodes.j.inputs.length,0);assert.equal(h.writes.length,0);
assert.match(h.markup,/data-author-tab="content"/);
h.dialogs.push(null);h.click('start_input_delete',{id:'incident_at'});await flush();assert.equal(h.draft().definition.nodes.p.inputs.length,1);
h.click('save');await flush();assert.equal(h.writes[0].definition.nodes.p.inputs[0].id,'incident_at');
})().catch(e=>{console.error(e);process.exitCode=1;});
""")

    def test_earlier_reservations_are_listed_in_history_and_can_only_be_stopped(self):
        self.run_contract(r"""
(async()=>{
const h=harness(),record=h.workflows.get('w');record.draft.mode='periodic';record.published=copy(record.draft);record.published_version=2;
h.state.operations={schedules:[{id:'s1',workflow_id:'w',version:2,factory_id:'',identity_user_id:'a',enabled:true,revision:3},
  {id:'s0',workflow_id:'w',version:1,factory_id:'f1',identity_user_id:'a',enabled:false,revision:1},
  {id:'sx',workflow_id:'other',version:1,factory_id:'',identity_user_id:'a',enabled:true,revision:1}]};h.render();
assert.doesNotMatch(h.markup,/이전에 맡긴 자동 실행/);
h.click('tab',{tab:'history'});await flush();
assert.match(h.markup,/이전에 맡긴 자동 실행/);assert.match(h.markup,/게시 v2 · 전체 공장 · 실행 계정 a/);assert.doesNotMatch(h.markup,/게시 v1 · f1/);
assert.doesNotMatch(h.markup,/data-author-action="schedule_create"|게시 버전 예약 만들기/);
h.dialogs.push({});h.click('schedule_disable',{id:'s1'});await flush();
assert.equal(h.operations.length,1);assert.equal(h.operations[0].action,'schedule_disable');assert.equal(h.operations[0].schedule_id,'s1');assert.equal(h.operations[0].expected_revision,3);
h.click('schedule_create');await flush();assert.equal(h.operations.length,1);assert.equal(h.writes.length,0);
h.state.operations={schedules:[]};h.render();assert.doesNotMatch(h.markup,/이전에 맡긴 자동 실행/);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")

    def test_read_retry_is_explicit_bounded_draft_policy_without_default_registration(self):
        self.run_contract(r"""
(async()=>{
const h=harness();await h.node();assert.doesNotMatch(h.markup,/name="read_retry_count"/);
h.field('job_guidance','도구 연결 전 안내만 수정');assert.equal(h.draft().definition.nodes.j.read_retry,undefined);
h.click('save');await flush();assert.equal(h.writes[0].definition.nodes.j.read_retry,undefined);
// The approved A12 editor hides legacy retry controls; reading or editing guidance
// must neither create a retry policy nor erase an explicitly stored policy.
const record=h.workflows.get('w');record.draft.nodes.j.mode='tool';record.draft.nodes.j.read_retry={count:2,deadline_seconds:45};h.render();await h.node();
assert.doesNotMatch(h.markup,/name="read_retry_count"|name="read_retry_deadline"/);
assert.deepEqual(h.draft().definition.nodes.j.read_retry,{count:2,deadline_seconds:45});
h.field('job_guidance','별도 안내 수정');h.click('save');await flush();
assert.deepEqual(h.writes[1].definition.nodes.j.read_retry,{count:2,deadline_seconds:45});
await h.open('q');await h.open('w');assert.deepEqual(h.draft().definition.nodes.j.read_retry,{count:2,deadline_seconds:45});
assert.equal(h.operations.length,0);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")

    def test_ai_completion_kind_is_explicit_preserved_and_saved_under_current_revision(self):
        self.run_contract(r"""
(async()=>{
const h=harness();h.workflows.get('w').draft.nodes.j.mode='ai';h.workflows.get('w').draft.nodes.j.result_block='ai_review';h.render();await h.node();
assert.equal(h.draft().definition.nodes.j.completion?.kind,undefined);h.field('job_guidance','검토 안내만 변경');assert.equal(h.draft().definition.nodes.j.completion?.kind,undefined);
h.field('completion_kind','delivery','change');assert.equal(h.draft().definition.nodes.j.completion.kind,'delivery');assert.equal(h.writes.length,0);
h.click('save');await flush();assert.equal(h.writes[0].expected_revision,1);assert.equal(h.writes[0].definition.nodes.j.completion.kind,'delivery');assert.equal(h.draft().revision,2);
h.field('completion_rule','송부 결과 근거 확인');assert.equal(h.draft().definition.nodes.j.completion.kind,'delivery');
await h.open('q');await h.open('w');assert.equal(h.draft().definition.nodes.j.completion.kind,'delivery');
h.state.workflow.can_manage=false;h.render();h.field('completion_kind','review','change');assert.equal(h.draft().definition.nodes.j.completion.kind,'delivery');h.click('save');await flush();assert.equal(h.writes.length,1);
h.state.workflow.can_manage=true;h.render();h.field('completion_kind','review','change');assert.equal(h.draft().definition.nodes.j.completion.kind,undefined);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")

    def test_normalized_published_definition_never_replaces_the_authoring_draft(self):
        self.run_contract(r"""
(async()=>{
const h=harness(),record=h.workflows.get('w'),published=copy(record.draft);
record.published_version=1;record.published=copy(published);record.definition=copy(published);
record.draft.nodes.j.mode='tool';record.draft.nodes.j.instructions='게시 이후의 저장 초안';
h.render();await h.node();assert.equal(h.draft().definition.nodes.j.mode,'tool');assert.doesNotMatch(h.markup,/name="read_retry_count"/);
h.field('job_guidance','현재 편집 중인 초안');h.render();assert.equal(h.draft().definition.nodes.j.instructions,'현재 편집 중인 초안');assert.equal(record.published.nodes.j.mode,'human');
h.click('save');await flush();assert.equal(h.writes[0].definition.nodes.j.mode,'tool');assert.equal(h.writes[0].definition.nodes.j.instructions,'현재 편집 중인 초안');
assert.equal(h.writes[0].publication_state,'published');assert.equal(record.published.nodes.j.mode,'tool');assert.equal(record.published.nodes.j.instructions,'현재 편집 중인 초안');assert.equal(record.definition.nodes.j.instructions,'원래 안내');
h.render();assert.equal(h.draft().definition.nodes.j.mode,'tool');assert.equal(h.draft().dirty,false);
const wrapped=copy(record.draft);wrapped.name='중첩 초안';record.draft={definition:wrapped};h.render();assert.equal(h.draft().definition.name,'중첩 초안');
})().catch(e=>{console.error(e);process.exitCode=1;});
""")

    def test_workflow_selection_ignores_previous_response_and_preserves_private_dirty_drafts(self):
        self.run_contract(r"""
(async()=>{
const h=harness();await h.node();h.field('job_guidance','W 미저장 글');
// Launcher select changes the selection before its new HTTP read resolves.
h.selection.workflow_id='q';h.render();assert.equal(h.draft().definition.id,'q');assert.equal(h.draft().definition.nodes.j.instructions,'원래 안내');
await h.node();h.field('job_guidance','Q 미저장 글');h.selection.workflow_id='w';h.state.workflow=h.workflows.get('q');h.render();assert.equal(h.draft().definition.id,'w');assert.equal(h.draft().definition.nodes.j.instructions,'W 미저장 글');
h.selection.workflow_id='q';h.state.workflow=h.workflows.get('w');h.render();assert.equal(h.draft().definition.id,'q');assert.equal(h.draft().definition.nodes.j.instructions,'Q 미저장 글');assert.equal(h.writes.length,0);
const pending=deferred();h.callbacks.read=()=>pending.promise;h.selection.workflow_id='not-in-list';h.render();assert.equal(h.draft().definition,null);assert.match(h.markup,/절차를 읽고 있습니다/);assert.doesNotMatch(h.markup,/Q 미저장 글|W 미저장 글/);
pending.resolve({workflow:{id:'not-in-list',revision:1,can_manage:true,draft:definition('not-in-list')}});await flush();assert.equal(h.draft().definition.id,'not-in-list');assert.equal(h.draft().dirty,false);assert.equal(h.writes.length,0);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")
