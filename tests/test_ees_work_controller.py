"""Controller behavior against mocked native/HTTP boundaries, not browser E2E."""

import json
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = ROOT / "branding/ees/ui/ees-work-launcher.js"

NODE_CONTROLLER = r"""
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const copy = value => JSON.parse(JSON.stringify(value));
const catalog = {
  version: 4, systems: ['EMS'], sites: {f1: {id: 'f1', name: '공장 1'}},
  roots: {setup: ['p1']}, nodes: {
    p1: {id: 'p1', type: 'p', category: 'setup', children: ['t1']},
    t1: {id: 't1', type: 't', parent: 'p1', children: ['j1', 'j2']},
    j1: {id: 'j1', type: 'j', parent: 't1', mode: 'tool'},
    j2: {id: 'j2', type: 'j', parent: 't1', mode: 'manual'}
  }
};
const makeCase = (revision = 1) => ({
  id: 'case-1', chat_id: '', process_id: 'p1', selected_id: 'j1', revision,
  version: 4, category: 'setup', site: {id: 'f1'}, system: 'EMS',
  definition: copy(catalog), tree_nodes: copy(catalog.nodes), status: 'ready'
});
const result = (run = null) => ({ok: true, case: run, cases: run ? [run] : [], catalog: copy(catalog)});
async function setup(options = {}) {
  const events = {}, frames = [], requests = [], renders = [], adoptions = [], confirmations = [], restores = [], viewEvents = [], readiness = [];
  const timers = new Map(); let nextTimer = 0;
  const nativeDraft = {prompt: '미저장 업무 질문', files: [{id: 'attachment-1'}]};
  let confirmed = true, nativeReady = options.nativeReady !== false;
  let state = options.state || result(), callbacks, resets = 0, actionHandler;
  let edits = {nodeId: 'j1', inputsChanged: false, documentChanged: false, conflict: false};
  const location = {pathname: '/', search: '?ees_site=f1&ees_system=EMS&ees_process=p1&ees_node=j1&ees_version=4'};
  function setRoute(url) { const parsed = new URL(url, 'https://example.test'); location.pathname = parsed.pathname; location.search = parsed.search; }
  if (options.route) setRoute(options.route);
  const on = (name, fn) => { (events[name] ||= []).push(fn); };
  const fire = (name, details = {}) => {
    const event = {type: name, target: {}, preventDefault() {this.defaultPrevented = true;},
      stopImmediatePropagation() {this.propagationStopped = true;}, ...details};
    (events[name] || []).forEach(fn => fn(event)); return event;
  };
  const capture = snapshot => renders.push(snapshot);
  const view = new Proxy({
    render: capture, renderNavigator: capture, renderPanel: capture,
    prepare: () => readiness.push(callbacks.scopeReady()), sync: () => readiness.push(callbacks.scopeReady()),
    updateScopeReadiness: () => readiness.push(callbacks.scopeReady()),
    readJobEdits: () => edits,
    adoptPreviewDraft: (caseId, nodeId) => adoptions.push([caseId, nodeId]),
    reset: () => { resets++; }, handleEvent: event => {viewEvents.push(event); return {handled: false};}
  }, {get: (target, key) => target[key] || (() => {})});
  const designer = new Proxy({handleEvent: () => ({handled: false})}, {get: (target, key) => target[key] || (() => {})});
  const window = {
    addEventListener: on, removeEventListener: () => {}, crypto: {randomUUID: () => 'request-' + requests.length},
    __eesNativeDraftV1: {ready: () => nativeReady, read: () => copy(nativeDraft),
      restore: async value => {restores.push(value); return true;}, flush: () => {}}
  };
  const document = {
    querySelector: selector => selector === '#sidebar-new-chat-button' ? {} : null,
    addEventListener: () => {}, documentElement: {}, body: {append: () => {}},
    createElement: () => ({click() {setRoute(this.href); fire('popstate');}, remove() {}})
  };
  const storage = new Map([['token', 'test-user']]);
  const localStorage = {getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key)};
  const context = {
    confirm: message => {confirmations.push(message); return confirmed;},
    window, document, location, localStorage, sessionStorage: localStorage,
    URLSearchParams,
    setTimeout: options.fakeTimers ? ((fn,delay) => {timers.set(++nextTimer,{fn,delay});return nextTimer;}) : setTimeout,
    clearTimeout: options.fakeTimers ? (id => timers.delete(id)) : clearTimeout,
    requestAnimationFrame: fn => frames.push(fn),
    MutationObserver: class {observe() {}},
    workUI: {dialog: async () => false, categories: {setup: '구축'}, finished: run => run.status === 'done', lineage: (id, data) => {
      const chain = []; while (id && data?.nodes[id]) {chain.unshift(data.nodes[id]); id = data.nodes[id].parent;} return chain;
    }},
    createWorkView: options => {callbacks = options.callbacks; return view;},
    createWorkDesigner: () => designer,
    fetch: async (url, options) => {
      const body = options.body ? JSON.parse(options.body) : null;
      requests.push({url, body});
      const answer = body && actionHandler ? await actionHandler(body) : state;
      return {ok: answer.ok !== false, json: async () => copy(answer)};
    }
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(input.source, 'utf8'), context, {timeout: 2000});
  async function settle() {
    for (let i = 0; i < 8; i++) {while (frames.length) frames.shift()(); await new Promise(resolve => setImmediate(resolve));}
  }
  await settle();
  return {
    api: window.__eesNativeWorkV1, callbacks, requests, renders, adoptions, confirmations,
    nativeDraft, restores, location, fire, viewEvents, readiness,
    setNativeReady: value => {nativeReady = value;},
    pendingTimers: () => [...timers.values()].map(timer => timer.delay),
    fireTimer: async () => {const [id,timer] = [...timers.entries()][0];timers.delete(id);timer.fn();await settle();},
    setConfirmed: value => {confirmed = value;},
    posts: () => requests.filter(request => request.body).map(request => request.body),
    latest: () => renders.at(-1), resets: () => resets,
    setState: value => {state = value;}, setAction: fn => {actionHandler = fn;},
    setEdits: value => {edits = value;}, edits: () => edits,
    route: url => {setRoute(url); fire('popstate');}, settle
  };
}
const scenarios = {
  async native_draft_completion_updates_controls_without_dom_mutation() {
    const h = await setup({nativeReady: false, fakeTimers: true});
    assert.equal(h.readiness.at(-1), false);
    const beforeRequests = h.requests.length, beforeDraft = copy(h.nativeDraft);
    assert.deepEqual(h.pendingTimers(), [50], 'Only one route readiness check is pending');
    await h.fireTimer();
    assert.deepEqual(h.pendingTimers(), [50]); assert.equal(h.readiness.at(-1), false);
    h.setNativeReady(true);
    assert.equal(h.readiness.at(-1), false, 'Store-only readiness changes leave the last rendered controls pending');
    await h.fireTimer();
    assert.equal(h.readiness.at(-1), true, 'Native readiness must update controls without a DOM mutation');
    assert.deepEqual(h.pendingTimers(), [], 'Ready editors do not keep polling');
    assert.equal(h.requests.length, beforeRequests, 'Readiness refresh does not fetch or write workflow state');
    assert.deepEqual(h.nativeDraft, beforeDraft);
    assert.equal(h.restores.length, 0);
  },
  async native_readiness_wait_cancels_when_leaving_chat_or_logging_out() {
    for (const route of ['/workspace/models', '/auth']) {
      const h = await setup({nativeReady: false, fakeTimers: true});
      assert.deepEqual(h.pendingTimers(), [50]);
      h.route(route); await h.settle();
      assert.deepEqual(h.pendingTimers(), [], 'Navigation and cleanup must cancel the old readiness wait');
      assert.equal(h.posts().length, 0);
    }
  },
  async first_chat_is_read_only() {
    const h = await setup();
    const ticket = h.api.beginChatCreation(); assert.ok(ticket);
    h.api.finishChatCreation(ticket, 'chat-1'); h.route('/c/chat-1');
    const captured = copy(h.api.selection('chat-1'));
    assert.equal(captured.kind, 'published');
    assert.deepEqual(captured.selection, {site_id: 'f1', system: 'EMS', process_id: 'p1', node_id: 'j1', version: 4});
    await h.settle();
    assert.deepEqual(copy(h.api.selection('chat-1')), captured);
    assert.equal(h.posts().length, 0, 'Reading and first chat creation must not create or bind a case');
  },
  async captured_preview_stays_with_its_chat() {
    const h = await setup(), ticket = h.api.beginChatCreation();
    h.api.finishChatCreation(ticket, 'chat-1'); h.route('/c/chat-1'); await h.settle();
    const original = copy(h.api.selection('chat-1'));
    assert.equal(original.kind, 'published');
    const draftBefore = copy(h.nativeDraft), restoresBefore = h.restores.length;
    await h.callbacks.selectWork('j2');
    assert.equal(h.location.pathname, '/c/chat-1');
    assert.deepEqual(h.nativeDraft, draftBefore, 'Same-chat selection preserves native text and files');
    assert.equal(h.restores.length, restoresBefore, 'Same-chat selection must not replace the native composer');
    assert.deepEqual(copy(h.api.selection('chat-1')).selection,
      {...original.selection, node_id: 'j2'}, 'Factory, system, process, and version remain scoped to the conversation');
    await h.callbacks.selectWork('j1');
    h.route('/c/unrelated-chat'); await h.settle();
    assert.deepEqual(copy(h.api.selection('unrelated-chat')), {ok: true, kind: 'none'},
      'A completed first-chat preview capture must not leak selection into another chat');
    h.route('/c/chat-1'); await h.settle();
    assert.deepEqual(copy(h.api.selection('chat-1')), original,
      'Returning to the original chat should recover its own saved procedure selection');
    await h.callbacks.selectWork('j2');
    const updated = copy(h.api.selection('chat-1')); assert.equal(updated.selection.node_id, 'j2');
    h.route('/'); await h.settle(); h.route('/c/chat-1'); await h.settle();
    assert.deepEqual(copy(h.api.selection('chat-1')), updated,
      'A consumed first-chat ticket must not overwrite later selection when returning from the root route');
    assert.equal(h.posts().length, 0);
  },
  async response_loss_reuses_first_write() {
    const h = await setup(); let attempts = 0;
    h.setAction(() => {if (++attempts === 1) throw new Error('response lost'); return result(makeCase(2));});
    assert.equal(await h.callbacks.saveInputs({asset: 'A'}, 'j1'), null);
    await h.callbacks.saveInputs({asset: 'A'}, 'j1');
    const [first, retry] = h.posts();
    assert.deepEqual(retry, first, 'Uncertain response retries must preserve the full intent and request ID');
    assert.deepEqual(first.scope, {site_id: 'f1', system: 'EMS', process_id: 'p1', version: 4});
    assert.equal(first.case_id, ''); assert.equal(first.node_id, 'j1'); assert.equal(first.expected_revision, 0);
    assert.equal(first.action, 'update_inputs'); assert.ok(first.request_id);
    assert.equal(h.latest().selectedCaseId, 'case-1');
    assert.deepEqual(h.adoptions, [['case-1', 'j1']]);
  },
  async partial_failure_keeps_created_case_and_draft() {
    const h = await setup(), draft = {nodeId: 'j1', inputsChanged: true, inputs: {asset: 'A'}};
    h.setEdits(draft);
    h.setAction(() => ({...result(makeCase(1)), ok: false, error: {code: 'invalid_inputs', message: '입력을 확인해 주세요.'}}));
    await h.callbacks.saveInputs({asset: 'A'}, 'j1');
    assert.equal(h.latest().selectedCaseId, 'case-1');
    assert.match(h.latest().errorMessage, /입력을 확인/);
    assert.deepEqual(h.adoptions, [['case-1', 'j1']]); assert.equal(h.edits(), draft);
    h.setAction(() => result(makeCase(2)));
    await h.callbacks.saveInputs({asset: 'B'}, 'j1');
    const next = h.posts()[1]; assert.equal(next.case_id, 'case-1'); assert.equal(next.expected_revision, 1);
    assert.equal(next.scope, undefined, 'Recovery must target the created case instead of creating another');
  },
  async revision_conflict_refreshes_without_resetting_draft() {
    const current = makeCase(3); current.chat_id = 'chat-1';
    const h = await setup({state: result(current), route: '/c/chat-1'});
    const draft = {nodeId: 'j1', inputsChanged: true, inputs: {asset: 'local'}};
    h.setEdits(draft); const beforeResets = h.resets(), beforeReads = h.requests.length;
    const newest = {...current, revision: 4}; h.setState(result(newest));
    h.setAction(() => ({ok: false, error: {code: 'revision_conflict', message: '저장된 내용이 변경되었습니다.'}}));
    await h.callbacks.saveInputs(draft.inputs, 'j1');
    assert.ok(h.requests.length > beforeReads + 1, 'A conflict must fetch current saved values');
    assert.equal(h.latest().state.case.revision, 4); assert.match(h.latest().errorMessage, /변경되었습니다/);
    assert.equal(h.edits(), draft); assert.equal(h.resets(), beforeResets);
  },
  async navigation_during_write_keeps_new_selection() {
    const h = await setup(); let complete;
    h.setAction(() => new Promise(resolve => {complete = resolve;}));
    const writing = h.callbacks.saveInputs({asset: 'A'}, 'j1');
    await h.callbacks.selectWork('j2');
    complete(result(makeCase(2))); await writing; await h.settle();
    assert.equal(h.latest().selectedId, 'j2', 'A late result must not reopen the originating job');
    assert.equal(h.latest().selectedCaseId, ''); assert.deepEqual(h.adoptions, []);
  },
  async preview_reselection_survives_refresh_and_version_change() {
    const h = await setup(), updated = result(); updated.catalog.version = 5;
    h.setState(updated); await h.api.refresh();
    assert.equal(h.api.selection('').selection.version, 4, 'An old preview cannot silently adopt a new version');
    await h.callbacks.selectWork('j2'); await h.api.refresh();
    assert.equal(h.latest().selectedId, 'j2'); assert.equal(h.api.selection('').selection.version, 5);
    assert.equal(h.posts().length, 0);
  },
  async next_job_navigation_preserves_case_and_never_runs() {
    const current = makeCase(3); current.chat_id = 'chat-1';
    current.jobs = {j1: {status: 'passed', inputs: {asset: 'A'}, history: [{attempt: 1, status: 'failed'}, {attempt: 2, status: 'passed'}]}};
    const h = await setup({state: result(current), route: '/c/chat-1'});
    const draftBefore = copy(h.nativeDraft), jobBefore = copy(current.jobs.j1);
    h.setAction(body => result({...current, selected_id: body.node_id, revision: current.revision + 1}));
    await h.callbacks.selectWork('j2');
    assert.deepEqual(h.posts().map(body => body.action), ['select'],
      'Opening the next task only selects it; it neither runs nor confirms it');
    assert.equal(h.posts()[0].case_id, current.id); assert.equal(h.posts()[0].chat_id, 'chat-1');
    assert.equal(h.latest().selectedId, 'j2'); assert.equal(h.location.pathname, '/c/chat-1');
    assert.deepEqual(h.latest().state.case.jobs.j1, jobBefore, 'Results and the failed attempt remain visible');
    assert.deepEqual(h.nativeDraft, draftBefore, 'Conversation text and attachments are preserved');
    assert.equal(h.confirmations.length, 0);
  },
  async dirty_and_conflicting_jobs_cannot_run() {
    const h = await setup();
    h.setEdits({nodeId: 'j1', inputsChanged: true}); await h.callbacks.runJob('j1');
    assert.match(h.latest().errorMessage, /먼저 반영/);
    h.setEdits({nodeId: 'j1', conflict: true}); await h.callbacks.runJob('j1');
    assert.match(h.latest().errorMessage, /저장된 내용이 변경/);
    h.setEdits({nodeId: 'j2'}); await h.callbacks.saveInputs({asset: 'A'}, 'j1');
    assert.match(h.latest().errorMessage, /작성한 업무/); assert.equal(h.posts().length, 0);
  },
  async parent_run_skips_failed_jobs_and_manual_run_is_explicit() {
    const h = await setup(); h.setAction(() => result(makeCase(2)));
    await h.callbacks.runJob('p1'); assert.deepEqual(h.posts()[0].payload, {retry_failed: false});
    h.setEdits({nodeId: 'j2'}); await h.callbacks.runJob('j2');
    assert.deepEqual(h.posts()[1].payload, {confirm: true}); assert.equal(h.posts()[1].node_id, 'j2');
  },
  async manual_confirmation_can_be_cancelled_without_a_write() {
    const h = await setup(); h.setEdits({nodeId: 'j2'}); h.setConfirmed(false);
    await h.callbacks.runJob('j2');
    assert.equal(h.confirmations.length, 1);
    assert.equal(h.posts().length, 0);
  },
  async repeated_save_activation_does_not_become_execution() {
    const h = await setup(); let complete;
    h.setAction(() => new Promise(resolve => {complete = resolve;}));
    const writing = h.callbacks.saveInputs({asset: 'A'}, 'j1');
    await h.callbacks.runJob('j1', {detail: 2});
    complete(result(makeCase(2))); await writing;
    h.setAction(() => result(makeCase(3)));
    await h.callbacks.runJob('j1', {detail: 2});
    assert.deepEqual(h.posts().map(body => body.action), ['update_inputs'],
      'The continuation of a save double click must not execute after the response renders');
    await h.callbacks.runJob('j1', {detail: 1});
    assert.deepEqual(h.posts().map(body => body.action), ['update_inputs', 'run']);
    assert.equal(h.posts()[1].node_id, 'j1'); assert.equal(h.posts()[1].case_id, 'case-1');
  },
  async held_enter_cannot_escape_saved_form_after_render() {
    const h = await setup();
    const inputTarget = {closest: selector => selector.includes('#ees-work-inputs') ? {} : null};
    const first = h.fire('keydown', {key: 'Enter', repeat: false, target: inputTarget});
    assert.equal(first.defaultPrevented, undefined, 'Initial Enter keeps normal form submission');
    const before = h.viewEvents.length;
    const repeated = h.fire('keydown', {key: 'Enter', repeat: true, target: {}});
    assert.equal(repeated.defaultPrevented, true);
    assert.equal(repeated.propagationStopped, true,
      'A key held during a render must not fall through to the native chat composer');
    assert.equal(h.viewEvents.length, before, 'Repeated activation cannot reach a new run control');
    h.fire('keyup', {key: 'Enter'});
    assert.equal(h.fire('keydown', {key: 'Enter', repeat: true}).defaultPrevented, undefined,
      'Releasing the work key restores unrelated native key handling');
    h.fire('keydown', {key: 'Enter', repeat: false, target: inputTarget}); h.fire('blur');
    assert.equal(h.fire('keydown', {key: 'Enter', repeat: true}).defaultPrevented, undefined,
      'Leaving the browser clears a potentially missed keyup');
    assert.equal(h.posts().length, 0);
  },
  async held_space_on_mutation_control_stays_blocked_until_release() {
    for (const key of [' ', 'Spacebar']) {
      const h = await setup(), beforeDraft = copy(h.nativeDraft);
      const saveTarget = {closest: selector => selector === '#ees-work-panel button[data-mutation]' ? {} : null};
      const first = h.fire('keydown', {key, repeat: false, target: saveTarget});
      assert.equal(first.defaultPrevented, undefined,
        'Initial Space retains the normal button keyup activation');
      const beforeEvents = h.viewEvents.length;
      for (const target of [saveTarget, {}]) {
        const repeated = h.fire('keydown', {key, repeat: true, target});
        assert.equal(repeated.defaultPrevented, true);
        assert.equal(repeated.propagationStopped, true,
          'Held Space cannot reach another control or the native composer after focus is lost');
      }
      assert.equal(h.viewEvents.length, beforeEvents);
      const released = h.fire('keyup', {key, target: saveTarget});
      assert.equal(released.defaultPrevented, undefined,
        'Releasing Space must not suppress the intended save button activation');
      assert.equal(h.fire('keydown', {key, repeat: true}).defaultPrevented, undefined,
        'Releasing the work key restores unrelated native Space handling');
      h.fire('keydown', {key, repeat: false, target: saveTarget}); h.fire('blur');
      assert.equal(h.fire('keydown', {key, repeat: true}).defaultPrevented, undefined,
        'Leaving the browser clears a missed Space keyup');
      assert.equal(h.posts().length, 0);
      assert.deepEqual(h.nativeDraft, beforeDraft);
    }
  }
};
scenarios[input.scenario]().then(() => process.stdout.write('ok\n')).catch(error => {console.error(error); process.exitCode = 1;});
"""


@unittest.skipUnless(shutil.which("node"), "Node is required for controller boundary regressions.")
class WorkControllerTests(unittest.TestCase):
    def check_scenario(self, scenario):
        result = subprocess.run(
            [shutil.which("node"), "-e", NODE_CONTROLLER],
            input=json.dumps({"source": str(CONTROLLER), "scenario": scenario}),
            capture_output=True, encoding="utf-8", timeout=10, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "ok")

    def test_first_chat_is_read_only(self):
        self.check_scenario("first_chat_is_read_only")

    def test_native_draft_completion_updates_controls_without_dom_mutation(self):
        self.check_scenario("native_draft_completion_updates_controls_without_dom_mutation")

    def test_native_readiness_wait_cancels_when_leaving_chat_or_logging_out(self):
        self.check_scenario("native_readiness_wait_cancels_when_leaving_chat_or_logging_out")

    def test_captured_preview_stays_with_its_chat(self):
        self.check_scenario("captured_preview_stays_with_its_chat")

    def test_response_loss_reuses_first_write(self):
        self.check_scenario("response_loss_reuses_first_write")

    def test_partial_failure_keeps_created_case_and_draft(self):
        self.check_scenario("partial_failure_keeps_created_case_and_draft")

    def test_revision_conflict_refreshes_without_resetting_draft(self):
        self.check_scenario("revision_conflict_refreshes_without_resetting_draft")

    def test_navigation_during_write_keeps_new_selection(self):
        self.check_scenario("navigation_during_write_keeps_new_selection")

    def test_preview_reselection_survives_refresh_and_version_change(self):
        self.check_scenario("preview_reselection_survives_refresh_and_version_change")

    def test_next_job_navigation_preserves_case_and_never_runs(self):
        self.check_scenario("next_job_navigation_preserves_case_and_never_runs")

    def test_dirty_and_conflicting_jobs_cannot_run(self):
        self.check_scenario("dirty_and_conflicting_jobs_cannot_run")

    def test_parent_run_skips_failed_jobs_and_manual_run_is_explicit(self):
        self.check_scenario("parent_run_skips_failed_jobs_and_manual_run_is_explicit")

    def test_manual_confirmation_can_be_cancelled_without_a_write(self):
        self.check_scenario("manual_confirmation_can_be_cancelled_without_a_write")

    def test_repeated_save_activation_does_not_become_execution(self):
        self.check_scenario("repeated_save_activation_does_not_become_execution")

    def test_held_enter_cannot_escape_saved_form_after_render(self):
        self.check_scenario("held_enter_cannot_escape_saved_form_after_render")

    def test_held_space_on_mutation_control_stays_blocked_until_release(self):
        self.check_scenario("held_space_on_mutation_control_stays_blocked_until_release")
