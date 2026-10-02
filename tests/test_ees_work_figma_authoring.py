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

    def test_modes_and_explicit_schedule_values_preserve_cas_without_seeding_examples(self):
        self.run_contract(r"""
(async()=>{
const h=harness(),original=copy(h.workflows.get('w').draft);
h.click('tab',{tab:'schedule'});await flush();
assert.deepEqual(h.draft().definition,original);assert.equal(h.draft().dirty,false);
assert.match(h.markup,/시작할 때 받는 값/);assert.doesNotMatch(h.markup,/2026-09-15|2주마다|대상 확정/);
h.click('run_mode',{id:'periodic'});await flush();
assert.equal(h.draft().definition.schedule,undefined);
assert.match(h.markup,/규칙을 게시하고 실행을 위임한 예약에서만/);assert.doesNotMatch(h.markup,/이후 회차는 직전 회차가 완료되면 열리며/);
h.field('frequency','weekly','change');h.field('interval','2');
h.field('weekday','1','change');h.field('anchor','2026-10-06T09:00');
h.field('timezone','Asia/Seoul');h.field('name_template','{date} 회차');
h.field('stage_start:t','-8');h.field('stage_end:t','-6');
h.field('opening','after_previous_closed','change');h.field('closing','after_last_stage','change');
h.field('non_working_days','notify_no_shift','change');
const schedule=copy(h.draft().definition.schedule);
assert.deepEqual(schedule,{frequency:'weekly',interval:2,weekday:1,anchor:'2026-10-06T09:00',timezone:'Asia/Seoul',name_template:'{date} 회차',stage_deadlines:{t:{offset_days:-8,end_offset_days:-6}},opening:'after_previous_closed',closing:'after_last_stage',non_working_days:'notify_no_shift'});
assert.equal(h.writes.length,0);h.click('save');await flush();
assert.equal(h.writes[0].action,'save_draft');assert.equal(h.writes[0].expected_revision,1);
assert.deepEqual(h.writes[0].definition.schedule,schedule);assert.equal(h.draft().dirty,false);
h.click('run_mode',{id:'emergency'});await flush();
assert.match(h.markup,/발생 시각·현상/);assert.doesNotMatch(h.markup,/name="anchor"/);
assert.deepEqual(h.draft().definition.schedule,schedule);
h.click('run_mode',{id:'periodic'});await flush();
assert.deepEqual(h.draft().definition.schedule,schedule);
h.field('frequency','monthly','change');assert.equal(h.draft().definition.schedule.weekday,undefined);
await h.open('q');await h.open('w');assert.equal(h.draft().definition.schedule.frequency,'monthly');
})().catch(e=>{console.error(e);process.exitCode=1;});
""")

    def test_preview_is_read_only_and_late_results_cannot_replace_edited_or_other_account_state(self):
        self.run_contract(r"""
(async()=>{
const h=harness(),record=h.workflows.get('w');record.draft.mode='periodic';record.draft.schedule={timezone:'Asia/Seoul',anchor:'2026-10-06T09:00',frequency:'weekly',interval:2};h.render();h.click('tab',{tab:'schedule'});await flush();
const waiting=deferred(),queries=[];h.callbacks.operationsCommand=async body=>{queries.push(copy(body));return waiting.promise;};
h.click('schedule_preview');await flush();assert.equal(queries[0].action,'schedule_preview');assert.equal(queries[0].workflow_id,'w');
assert.deepEqual(queries[0].definition,h.draft().definition);assert.equal(h.writes.length,0);assert.equal(h.draft().dirty,false);
h.field('interval','3');waiting.resolve({ok:true,preview:[{name:'OLD ONE'},{name:'OLD TWO'}]});await flush();assert.doesNotMatch(h.markup,/OLD ONE|OLD TWO/);
h.callbacks.operationsCommand=async()=>({ok:true,preview:[{date:'2026-10-06',name:'검증된 첫 회차'},{date:'2026-10-27',name:'검증된 다음 회차'}],warnings:[{code:'holiday_calendar_unavailable',message:'공휴일 달력 미연결'}]});
h.click('schedule_preview');await flush();assert.match(h.markup,/검증된 첫 회차/);assert.match(h.markup,/공휴일 달력 미연결/);assert.equal(h.writes.length,0);
const late=deferred();h.callbacks.operationsCommand=()=>late.promise;h.click('schedule_preview');await flush();h.state.capabilities.actor_id='b';h.render();await flush();late.resolve({ok:true,preview:[{name:'A PRIVATE'},{name:'A PRIVATE 2'}]});await flush();assert.doesNotMatch(h.markup,/A PRIVATE/);
h.state.workflow.can_manage=false;h.render();h.click('run_mode',{id:'emergency'});await flush();assert.equal(h.draft().definition.mode,'periodic');
})().catch(e=>{console.error(e);process.exitCode=1;});
""")

    def test_schedule_value_change_keeps_existing_controls_for_mouse_focus_transition(self):
        self.run_contract(r"""
(async()=>{
const h=harness();h.click('tab',{tab:'schedule'});h.click('run_mode',{id:'periodic'});await flush();
h.field('frequency','weekly','change');const form=h.forms['ew-author-schedule'];
const next=h.fields.find(field=>field.name==='name_template');
const query=h.host.querySelector.bind(h.host),preview={innerHTML:'변경 전 계산 날짜'};h.host.querySelector=selector=>selector==='.ew-schedule-preview'?preview:query(selector);
h.field('interval','2');h.field('interval','2','change');
assert.equal(h.forms['ew-author-schedule'],form,'blur/change must not replace the pending mouse click target');
assert.equal(h.fields.find(field=>field.name==='name_template'),next);
assert.match(preview.innerHTML,/일정이 바뀌었습니다/);assert.doesNotMatch(preview.innerHTML,/변경 전 계산 날짜/);
h.field('name_template','마우스로 입력한 {date} 회차','change');
assert.equal(h.forms['ew-author-schedule'],form);
h.click('save');await flush();assert.equal(h.writes[0].definition.schedule.interval,2);assert.equal(h.writes[0].definition.schedule.name_template,'마우스로 입력한 {date} 회차');
h.field('frequency','daily','change');assert.notEqual(h.forms['ew-author-schedule'],form);assert.doesNotMatch(h.markup,/name="weekday"/);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")

    def test_start_input_edit_and_published_schedule_use_real_definition_and_explicit_delegation(self):
        self.run_contract(r"""
(async()=>{
const h=harness();h.click('tab',{tab:'schedule'});await flush();
h.dialogs.push({id:'incident_at',name:'발생 시각',type:'datetime',scope:'run',required:true,options_source:'manual',options:''});
h.click('start_input_add');await flush();
assert.equal(h.draft().definition.nodes.p.inputs[0].id,'incident_at');assert.equal(h.draft().definition.nodes.p.inputs[0].scope,'run');assert.equal(h.draft().definition.nodes.j.inputs.length,0);assert.equal(h.writes.length,0);
h.dialogs.push(null);h.click('start_input_delete',{id:'incident_at'});await flush();assert.equal(h.draft().definition.nodes.p.inputs.length,1);
h.click('save');await flush();const record=h.workflows.get('w');
record.draft.mode='periodic';record.draft.schedule={timezone:'Asia/Seoul',anchor:'2026-10-06T09:00',frequency:'weekly',interval:2,weekday:1,name_template:'{date} 회차',stage_deadlines:{t:{offset_days:-8}},opening:'after_previous_closed',closing:'after_last_stage',non_working_days:'notify_no_shift'};record.published=copy(record.draft);record.published_version=2;h.render();
h.dialogs.push({grace_seconds:'300',delegated:false});h.click('schedule_create');await flush();
assert.equal(h.operations[0].action,'schedule_save');assert.equal(h.operations[0].schedule.lifecycle_enabled,false);assert.equal(h.operations[0].schedule.delegated,false);assert.equal(h.operations[0].schedule.version,2);assert.equal(h.operations[0].schedule.identity_user_id,'a');assert.deepEqual(h.operations[0].schedule.rule,record.published.schedule);assert.equal(h.operations[0].expected_revision,0);
h.dialogs.push({grace_seconds:'300',delegated:true});h.click('schedule_create');await flush();assert.equal(h.operations[1].schedule.lifecycle_enabled,true);assert.equal(h.operations[1].schedule.delegated,true);assert.deepEqual(h.operations[1].schedule.rule,record.published.schedule);
record.draft.schedule={timezone:'Asia/Seoul',anchor:'2026-10-06T09:00',frequency:'weekly',interval:2,name_template:'{date} 이름'};record.published=copy(record.draft);h.render();h.dialogs.push({grace_seconds:'300',delegated:true});h.click('schedule_create');await flush();assert.equal(h.operations[2].schedule.lifecycle_enabled,false);assert.deepEqual(h.operations[2].schedule.rule,record.published.schedule);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")

    def test_read_retry_is_explicit_bounded_draft_policy_without_default_registration(self):
        self.run_contract(r"""
(async()=>{
const h=harness();await h.node();assert.doesNotMatch(h.markup,/name="read_retry_count"/);
h.field('mode','tool','change');assert.equal(h.draft().definition.nodes.j.read_retry,undefined);
h.field('instructions','도구 설명만 수정');assert.equal(h.draft().definition.nodes.j.read_retry,undefined);
h.field('read_retry_count','2');assert.deepEqual(h.draft().definition.nodes.j.read_retry,{count:2,deadline_seconds:null});
h.field('read_retry_deadline','45');h.click('save');await flush();assert.deepEqual(h.writes[0].definition.nodes.j.read_retry,{count:2,deadline_seconds:45});
h.field('instructions','별도 안내 수정');assert.deepEqual(h.draft().definition.nodes.j.read_retry,{count:2,deadline_seconds:45});
h.field('read_retry_count','0');assert.equal(h.draft().definition.nodes.j.read_retry,undefined);
h.field('read_retry_count','2');h.field('read_retry_deadline','30');h.field('result_block','change_request','change');assert.doesNotMatch(h.markup,/name="read_retry_count"/);assert.deepEqual(h.draft().definition.nodes.j.read_retry,{count:2,deadline_seconds:30});
assert.equal(h.operations.length,0);assert.match(source,/min="0" max="3"/);assert.match(source,/min="1" max="300"/);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")

    def test_ai_completion_kind_is_explicit_preserved_and_saved_under_current_revision(self):
        self.run_contract(r"""
(async()=>{
const h=harness();h.workflows.get('w').draft.nodes.j.mode='ai';h.workflows.get('w').draft.nodes.j.result_block='ai_review';h.render();await h.node();
assert.equal(h.draft().definition.nodes.j.completion?.kind,undefined);h.field('instructions','검토 안내만 변경');assert.equal(h.draft().definition.nodes.j.completion?.kind,undefined);
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
h.render();await h.node();assert.equal(h.draft().definition.nodes.j.mode,'tool');assert.match(h.markup,/name="read_retry_count"/);
h.field('instructions','현재 편집 중인 초안');h.render();assert.equal(h.draft().definition.nodes.j.instructions,'현재 편집 중인 초안');
h.click('save');await flush();assert.equal(h.writes[0].definition.nodes.j.mode,'tool');assert.equal(h.writes[0].definition.nodes.j.instructions,'현재 편집 중인 초안');
assert.equal(record.published.nodes.j.mode,'human');assert.equal(record.definition.nodes.j.instructions,'원래 안내');
h.render();assert.equal(h.draft().definition.nodes.j.mode,'tool');assert.equal(h.draft().dirty,false);
const wrapped=copy(record.draft);wrapped.name='중첩 초안';record.draft={definition:wrapped};h.render();assert.equal(h.draft().definition.name,'중첩 초안');
})().catch(e=>{console.error(e);process.exitCode=1;});
""")

    def test_workflow_selection_ignores_previous_response_and_preserves_private_dirty_drafts(self):
        self.run_contract(r"""
(async()=>{
const h=harness();await h.node();h.field('instructions','W 미저장 글');
// Launcher select changes the selection before its new HTTP read resolves.
h.selection.workflow_id='q';h.render();assert.equal(h.draft().definition.id,'q');assert.equal(h.draft().definition.nodes.j.instructions,'원래 안내');
await h.node();h.field('instructions','Q 미저장 글');h.selection.workflow_id='w';h.state.workflow=h.workflows.get('q');h.render();assert.equal(h.draft().definition.id,'w');assert.equal(h.draft().definition.nodes.j.instructions,'W 미저장 글');
h.selection.workflow_id='q';h.state.workflow=h.workflows.get('w');h.render();assert.equal(h.draft().definition.id,'q');assert.equal(h.draft().definition.nodes.j.instructions,'Q 미저장 글');assert.equal(h.writes.length,0);
const pending=deferred();h.callbacks.read=()=>pending.promise;h.selection.workflow_id='not-in-list';h.render();assert.equal(h.draft().definition,null);assert.match(h.markup,/절차를 읽고 있습니다/);assert.doesNotMatch(h.markup,/Q 미저장 글|W 미저장 글/);
pending.resolve({workflow:{id:'not-in-list',revision:1,can_manage:true,draft:definition('not-in-list')}});await flush();assert.equal(h.draft().definition.id,'not-in-list');assert.equal(h.draft().dirty,false);assert.equal(h.writes.length,0);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")
