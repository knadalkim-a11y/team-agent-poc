// Production draft functions with minimal form stubs. This is not Native-app evidence.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../branding/ees/ui/ees-work-view.js'), 'utf8');
const plain = value => JSON.parse(JSON.stringify(value));

function fixture({saved = {config: {a: 1}, label: 'saved'}} = {}) {
  const controls = [
    {name: 'config', value: JSON.stringify(saved.config), defaultValue: JSON.stringify(saved.config)},
    {name: 'label', value: saved.label || '', defaultValue: saved.label || ''}
  ];
  const form = {controls, querySelectorAll: () => controls, contains: field => controls.includes(field)};
  const host = {querySelector: selector => selector === '#ees-work-inputs' ? form : null, querySelectorAll: () => []};
  const definition = {version: 1, sites: {site: {id: 'site'}}, nodes: {
    p: {id: 'p', type: 'p', execution_inputs: {properties: {config: {type: 'object'}, label: {type: 'string'}}}},
    j: {id: 'j', type: 'j', parent: 'p', execution: {kind: 'fixed'}},
    other: {id: 'other', type: 'j', parent: 'p', execution: {kind: 'fixed'}}
  }};
  const current = {id: 'case', version: 1, revision: 1, site: {id: 'site'}, system: 'EMS', execution_inputs: plain(saved), definition};
  const snapshot = {selectedId: 'j', selectedCaseId: 'case'};
  const context = {
    window: {}, document: {querySelector: () => null},
    workUI: {$: () => null, clone: plain, finished: () => false, lineage: (id, data) => [data.nodes.p, data.nodes[id]]},
    FormData: class { constructor(value) {this.form = value;} get(key) {return this.form.controls.find(field => field.name === key)?.value ?? null;} }
  };
  // Add only test accessors to the closure; the draft and guard functions execute unchanged.
  const marker = 'return Object.freeze({render,prepare,sync,';
  assert.ok(source.includes(marker), 'createWorkView return contract changed');
  const exposed = source.replace(marker, `return Object.freeze({_test:{
    setup:value=>{state=value.state;snapshot=value.snapshot;host=value.host;browsingSite='site';browsingSystem='EMS';runView='current';renderPanel=()=>{};},
    bind:()=>{renderedEditContext=editContext('j');},capture:captureJobEdits,
    raw:runtimeRawInputs,errors:runtimeInputErrors,versions:draftVersions
  },render,prepare,sync,`);
  vm.createContext(context);vm.runInContext(exposed, context);
  const view = vm.runInContext('createWorkView({callbacks:{}})', context);
  const state = {case: current, catalog: definition};
  view._test.setup({state, snapshot, host});
  const proposal = patch => ({proposalId: 'ai-1', source: 'Authorized fixture source', nodeId: 'j', caseId: 'case', revision: current.revision, expectedDraftVersion: view.draftVersion('j'), inputs: {config: {a: 2}}, ...patch});
  const type = (name, value) => {view._test.bind();const field = controls.find(item => item.name === name);field.value = value;view._test.capture(field);};
  const showAppliedForm = () => {const inputs = view.readJobEdits('j').inputs;for (const field of controls) {field.value = field.name === 'config' ? JSON.stringify(inputs.config) : inputs[field.name] || '';field.defaultValue = field.value;}view._test.bind();};
  return {view, current, state, snapshot, context, controls, proposal, type, showAppliedForm};
}

test('manual malformed JSON after AI input blocks undo without losing the raw draft', () => {
  const f = fixture(), proposal = f.proposal();
  assert.equal(f.view.applyAIDraft(proposal).ok, true);f.showAppliedForm();f.type('config', '{');
  const result = f.view.undoAIDraft(proposal), draft = f.view.readJobEdits('j');
  assert.equal(result.ok, false);assert.equal(draft.rawInputs.config, '{');
  assert.equal(draft.inputsChanged, true);assert.ok(draft.inputError);
  assert.equal(draft.aiReceipt.undone, false);
});

test('clearing an optional runtime field removes its typed value and marks the draft dirty', () => {
  const f = fixture();f.type('label', 'temporary');f.type('label', '');
  const draft = f.view.readJobEdits('j');
  assert.equal(Object.hasOwn(draft.inputs, 'label'), false);
  assert.equal(draft.inputsChanged, true);assert.equal(draft.rawInputs.label, '');
  assert.equal(f.current.execution_inputs.label, 'saved', 'draft capture must not mutate server values');
});

test('an independent concurrent input edit cannot be silently overwritten by a full draft replacement', () => {
  const f = fixture();f.type('config', '{"a":2}');
  f.current.execution_inputs.label = 'new server value';f.current.revision = 2;
  const draft = f.view.readJobEdits('j');
  assert.ok(draft.conflict || draft.inputs.label === 'new server value', 'stale untouched label must conflict or rebase');
});

test('AI undo restores the previous draft including an explicitly cleared optional field', () => {
  const f = fixture();f.type('label', '');
  const proposal = f.proposal();assert.equal(f.view.applyAIDraft(proposal).ok, true);f.showAppliedForm();
  assert.equal(f.view.undoAIDraft(proposal).ok, true);
  const draft = f.view.readJobEdits('j');
  assert.deepEqual(plain(draft.inputs.config), {a: 1});
  assert.equal(Object.hasOwn(draft.inputs, 'label'), false);
  assert.equal(draft.aiReceipt.undone, true);
});

test('a proposal captured before user input is rejected without changing that input', () => {
  const f = fixture(), proposal = f.proposal();f.type('label', 'user edit');
  const result = f.view.applyAIDraft(proposal);
  assert.equal(result.ok, false);assert.equal(result.code, 'draft_changed');
  assert.equal(f.view.readJobEdits('j').inputs.label, 'user edit');
});

test('late AI proposals cannot cross selected job or permission/read-error boundaries', () => {
  for (const change of ['node', 'recordLookupError', 'executionError']) {
    const f = fixture(), proposal = f.proposal();
    if (change === 'node')f.snapshot.selectedId = 'other';else f.snapshot[change] = {message: 'Current read is unavailable'};
    assert.equal(f.view.applyAIDraft(proposal).ok, false, change);
    assert.deepEqual(f.current.execution_inputs, {config: {a: 1}, label: 'saved'});
  }
});

test('AI undo after a server save/version change is rejected and preserves saved input', () => {
  const f = fixture(), proposal = f.proposal();assert.equal(f.view.applyAIDraft(proposal).ok, true);f.showAppliedForm();
  f.current.execution_inputs.config = {a: 2};f.current.revision = 2;
  const result = f.view.undoAIDraft({...proposal, revision: 2});
  assert.equal(result.ok, false);assert.deepEqual(f.current.execution_inputs.config, {a: 2});
});

test('preview adoption keeps malformed raw input when the first case is created elsewhere', () => {
  const f = fixture();f.state.case = null;f.snapshot.selectedCaseId = '';
  f.type('config', '{');
  assert.equal(f.view.readJobEdits('j').rawInputs.config, '{');
  f.view.adoptPreviewDraft('case', 'j');
  f.state.case = f.current;f.snapshot.selectedCaseId = 'case';f.view._test.bind();
  const draft = f.view.readJobEdits('j');
  assert.equal(draft.rawInputs?.config, '{');assert.ok(draft.inputError);
});

test('document-captured keyboard events reach the Assistant resizer control', () => {
  const f = fixture(), target = {closest: selector => selector === '#ees-work-resizer' ? target : null};
  const result = f.view.handleEvent({type: 'keydown', key: 'ArrowLeft', target, currentTarget: f.context.document});
  assert.equal(result.handled, true);assert.equal(result.preventDefault, true);
});

test('explicit discard clears malformed local input without changing saved values', () => {
  const f = fixture();f.type('config', '{');
  const target = {dataset: {action: 'discard_job_edits', nodeId: 'j'}, closest: selector => selector === '[data-action]' || selector === '[data-ees-work]' ? target : null};
  const result = f.view.handleEvent({type: 'click', target});
  assert.equal(result.handled, true);
  const draft = f.view.readJobEdits('j');
  assert.equal(draft.rawInputs, undefined);assert.equal(draft.inputError, undefined);
  assert.equal(draft.inputsChanged, false);assert.deepEqual(f.current.execution_inputs.config, {a: 1});
});
