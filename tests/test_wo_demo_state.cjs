/* Synthetic DOM/event contracts, not browser rendering or WebUI acceptance.
 * Executes the actual Python Tool's execute payload; no copied UI/state logic.
 * Run: node tests/test_wo_demo_state.cjs (Python 3.11+ available as `python`). */
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { spawnSync } = require('node:child_process');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const capturePython = `import asyncio, importlib.util, json, sys
from pathlib import Path
p = Path('agent-pack/skills/ems-work-order/scripts/wo_demo_tool.py')
s = importlib.util.spec_from_file_location('wo_demo_state_capture', p)
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
r = json.load(sys.stdin); captured = []
async def callback(event):
    captured.append(event['data']['code']); return {'ok': True}
async def run():
    kw = {'__event_call__': callback, '__metadata__': {'chat_id': r['chat_id']}}
    if r['action'] == 'view': await m.Tools().wo_demo_view(**kw)
    elif r['action'] == 'equipment': await m.Tools().ems_demo_find_equipment(**r['changes'], **kw)
    else: await m.Tools().wo_demo_update(r['revision'], r['changes'], **kw)
asyncio.run(run())
print(json.dumps({'code': captured[0], 'html': m.PANEL_HTML}))
`;
function capture(request) {
  const result = spawnSync(process.env.PYTHON || 'python', ['-c', capturePython], {
    cwd: root, input: JSON.stringify(request), encoding: 'utf8', timeout: 10000,
    env: { ...process.env, PYTHONUTF8: '1' },
  });
  assert.equal(result.status, 0, result.stderr || String(result.error || ''));
  return JSON.parse(result.stdout);
}
class Element {
  constructor(tag = 'div') {
    this.tagName = tag; this.children = []; this.parentElement = null;
    this.style = { minWidth: '' }; this.dataset = {}; this.attributes = {};
    this.events = {}; this.value = ''; this.hidden = false; this.disabled = false;
    const classes = new Set();
    this.classList = { contains: value => classes.has(value), toggle: (value, on) => on ? classes.add(value) : classes.delete(value) };
  }
  get isConnected() { return Boolean(this.connected || this.parentElement?.isConnected); }
  set textContent(value) { this._text = String(value); this.replaceChildren(); this.recordMutation(); }
  get textContent() { return (this._text || '') + this.children.map(c => c.textContent).join(''); }
  recordMutation() {
    if (!this.isConnected) return;
    let root = this; while (root.parentElement) root = root.parentElement;
    root.onMutation?.({ target: this });
  }
  append(...nodes) { nodes.forEach(node => { node.remove(); node.parentElement = this; this.children.push(node); this.recordMutation(); }); }
  replaceChildren(...nodes) { [...this.children].forEach(node => node.remove()); this.append(...nodes); }
  remove() { const parent = this.parentElement; if (parent) parent.children = parent.children.filter(c => c !== this); this.parentElement = null; parent?.recordMutation(); }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  getBoundingClientRect() { return { width: this.rectWidth ?? (parseFloat(this.style.width) || this.clientWidth || 0) }; }
  setPointerCapture(id) { this.captureId = id; }
  hasPointerCapture(id) { return this.captureId === id; }
  releasePointerCapture(id) { if (this.captureId === id) this.captureId = null; }
  addEventListener(type, callback) { (this.events[type] ||= []).push(callback); }
  removeEventListener(type, callback) { this.events[type] = (this.events[type] || []).filter(c => c !== callback); }
  fire(type, values = {}) { (this.events[type] || []).forEach(callback => callback({ target: this, button: 0, pointerId: 1, preventDefault() {}, ...values })); }
  focus() { this.focused = true; }
  attachShadow() { this.shadowRoot = new Shadow(); return this.shadowRoot; }
}
class Shadow extends Element {
  set innerHTML(html) {
    this.ids = new Map(); this.origins = new Map();
    // Only the actual template's IDs, initial attributes and origin labels are
    // needed by this runtime. This deliberately is not a general HTML engine.
    for (const match of html.matchAll(/<([a-z][\w-]*)\b([^<>]*)>/gi)) {
      const attributes = Object.fromEntries([...match[2].matchAll(/([\w-]+)="([^"]*)"/g)].map(a => [a[1], a[2]]));
      if (!attributes.id && !attributes['data-origin-for']) continue;
      const element = new Element(match[1]); element.hidden = /\bhidden\b/.test(match[2]);
      element.value = attributes.value || ''; element.id = attributes.id;
      if (attributes.id) this.ids.set(attributes.id, element);
      if (attributes['data-origin-for']) this.origins.set(attributes['data-origin-for'], element);
      this.append(element);
    }
  }
  getElementById(id) { return this.ids.get(id) || null; }
  querySelector(selector) { return this.origins.get(selector.match(/data-origin-for="([^"]+)"/)?.[1]) || null; }
}
function environment({ layout = true, navigation = true } = {}) {
  const body = new Element('body'); body.connected = true;
  let row = new Element(), column = new Element(), anchor = new Element();
  row.clientWidth = 1200;
  body.append(row); row.append(column); column.append(anchor);
  const documentElement = new Element('html'), observers = [], window = new Element('window');
  window.innerWidth = 1440;
  if (navigation) window.navigation = new Element('navigation');
  const pendingMutations = []; body.onMutation = record => pendingMutations.push(record);
  const document = { body, documentElement, createElement: tag => new Element(tag), querySelector: selector => layout && selector === '#chat-container #chat-pane' ? anchor : null };
  class MutationObserver {
    constructor(callback) { this.callback = callback; observers.push(this); }
    observe(target) { this.active = true; this.target = target; }
    disconnect() { this.active = false; }
  }
  const sizeObservers = [];
  class ResizeObserver {
    constructor(callback) { this.callback = callback; sizeObservers.push(this); }
    observe() { this.active = true; }
    disconnect() { this.active = false; }
  }
  const location = { pathname: '/c/sample-chat' };
  const context = vm.createContext({ window, document, location, MutationObserver, ResizeObserver, getComputedStyle: node => ({ display: 'flex', position: node.style.position || 'static' }) });
  const host = () => row.children.find(node => node.id === 'ees-wo-demo-panel');
  const q = id => host()?.shadowRoot.getElementById(id);
  async function call(action = 'view', changes = {}, revision, chat_id = 'sample-chat') {
    const payload = capture({ action, changes, revision, chat_id });
    const result = await vm.runInContext('(async () => {\n' + payload.code + '\n})()', context);
    return JSON.parse(JSON.stringify(result));
  }
  const mutate = (records = []) => observers.filter(o => o.active && o.target === body).forEach(o => o.callback(records));
  return { window, location, get row() { return row; }, get column() { return column; }, body, host, q, call, context, sizeObservers, observers,
    divider: () => row.children.find(node => node.id === 'ees-wo-demo-resizer'),
    launcher: () => column.children.find(node => node.id === 'ees-work-panel-toggle'),
    mutate,
    flushMutations: () => {
      let deliveries = 0;
      while (pendingMutations.length) {
        assert.ok(++deliveries <= 10, 'Panel manager must settle after its own DOM mutations');
        mutate(pendingMutations.splice(0));
      }
      return deliveries;
    },
    replaceLayout: () => {
      const old = { row, column, anchor }; row.remove();
      row = new Element(); column = new Element(); anchor = new Element(); row.clientWidth = 1200;
      body.append(row); row.append(column); column.append(anchor);
      return old;
    },
    resize: () => sizeObservers.filter(o => o.active).forEach(o => o.callback()),
  };
}
const ok = result => { assert.equal(result.ok, true, JSON.stringify(result)); assert.equal(result.demo, true); return result; };
const bad = (result, code) => { assert.equal(result.ok, false); if (code) assert.equal(result.error.code, code); return result; };

(async () => {
  const env = environment(); let state = ok(await env.call());
  assert.equal(state.matches_count, 32); assert.equal(state.matches.length, 8);
  const firstHost = env.host(); assert.ok(firstHost); assert.equal(env.row.children.length, 3);
  bad(await env.call('update', { site: '천안', title: 'must not apply' }, state.revision), 'parent_required');
  assert.deepEqual(ok(await env.call()).fields, state.fields);
  assert.equal(ok(await env.call()).revision, state.revision);
  state = ok(await env.call('update', { corporation: '한국', site: '천안', shop: '조립', line: '조립 1라인', process: '권취' }, state.revision));
  assert.equal(state.matches_count, 1); const equipment = state.matches[0];
  state = ok(await env.call('update', { site: '울산' }, state.revision));
  assert.deepEqual([state.filters.shop, state.filters.line, state.filters.process], ['', '', '']);
  state = ok(await env.call('update', { equipment_id: equipment.id }, state.revision));
  assert.equal(state.equipment.id, equipment.id); assert.equal(env.q('form').hidden, false);
  env.q('choose-again').fire('click'); assert.equal(env.q('filters').hidden, false);
  env.q('results').children.find(node => node.dataset.equipmentId === equipment.id).fire('click');
  assert.equal(env.q('form').hidden, false);
  env.q('form').fire('submit');
  assert.equal(ok(await env.call()).phase, 'edit'); assert.equal(env.q('validation').hidden, false);
  console.log('PASS hierarchy, atomic rejection, equipment selection and required fields');

  state = ok(await env.call('update', { title: '모터 점검', description: 'AI 초안' }, state.revision));
  const stale = state.revision;
  env.q('description').value = '사용자가 직접 적은 소음'; env.q('description').fire('input');
  bad(await env.call('update', { description: 'stale overwrite' }, stale), 'revision_conflict');
  state = ok(await env.call()); assert.equal(state.fields.description, '사용자가 직접 적은 소음');
  state = ok(await env.call('update', { priority: '긴급' }, state.revision));
  assert.equal(state.fields.description, '사용자가 직접 적은 소음');
  env.q('undo').fire('click'); state = ok(await env.call());
  assert.equal(state.fields.priority, '일반'); assert.equal(state.fields.description, '사용자가 직접 적은 소음');
  state = ok(await env.call('update', { title: 'AI가 고친 제목' }, state.revision));
  env.q('description').value = '수동 입력은 지우지 않음'; env.q('description').fire('input');
  assert.equal(env.q('undo').hidden, true); env.q('undo').fire('click');
  state = ok(await env.call()); assert.equal(state.fields.description, '수동 입력은 지우지 않음');
  assert.equal(state.fields.title, 'AI가 고친 제목');
  const injection = '"; globalThis.EES_TEST_INJECTION=true; // </script><script>bad()</script>';
  state = ok(await env.call('update', { description: injection }, state.revision));
  assert.equal(state.fields.description, injection); assert.equal(env.q('description').value, injection);
  assert.equal(env.context.EES_TEST_INJECTION, undefined);
  state = ok(await env.call('update', { site: '울산' }, state.revision));
  assert.equal(state.equipment, null);
  env.q('results').children.find(node => node.dataset.equipmentId).fire('click');
  state = ok(await env.call()); assert.equal(state.equipment.site, '울산');
  assert.equal(state.fields.description, injection); assert.ok(state.message.includes('유지'));
  console.log('PASS shared manual/AI state, stale revision, undo and code-like text');

  env.q('form').fire('submit'); assert.equal(ok(await env.call()).phase, 'review');
  state = ok(await env.call('update', { priority: '긴급' }, state.revision));
  assert.equal(state.phase, 'edit'); assert.equal(env.q('review').hidden, true);
  env.q('issue').fire('click'); assert.equal(ok(await env.call()).phase, 'edit');
  env.q('form').fire('submit'); env.q('issue').fire('click');
  state = ok(await env.call()); assert.equal(state.phase, 'issued');
  assert.equal(env.q('result-number').textContent, 'WO-DEMO-0001');
  assert.ok(env.q('result-values').textContent.includes(injection));
  const issuedRevision = state.revision; env.q('issue').fire('click');
  assert.equal(ok(await env.call()).revision, issuedRevision);
  bad(await env.call('update', { title: 'cannot edit issued sample' }, issuedRevision), 'already_issued');
  console.log('PASS review invalidation, sample-only final click and duplicate protection');

  env.q('close').fire('click'); assert.equal(env.host(), undefined);
  assert.equal(ok(await env.call()).phase, 'issued'); assert.equal(env.host(), firstHost);
  env.location.pathname = '/c/second-chat'; env.mutate();
  assert.equal(env.host(), undefined); assert.equal(env.window.__eesWODemoV1, undefined);
  state = ok(await env.call('view', {}, undefined, 'second-chat'));
  assert.equal(state.equipment, null); assert.equal(state.fields.description, '');
  assert.notEqual(env.host(), firstHost);
  env.location.pathname = '/';
  bad(await env.call('view', {}, undefined, 'second-chat'), 'regular_chat_required');
  assert.equal(env.host(), undefined);
  const unsupported = environment({ layout: false });
  bad(await unsupported.call(), 'unsupported_layout');
  assert.equal(unsupported.row.children.length, 1); assert.equal(unsupported.window.__eesWODemoV1, undefined);
  console.log('PASS close/reopen, isolated new-chat state and unsupported routes/layout');

  const sized = environment(); let draft = ok(await sized.call());
  const initialRevision = draft.revision;
  const fields = { title: '설비 점검', type: '점검', priority: '일반', description: '선택한 설비 점검 요청' };
  draft = ok(await sized.call('update', { equipment_id: draft.matches[0].id, ...fields }, initialRevision));
  assert.equal(draft.revision, initialRevision + 1); assert.deepEqual(draft.fields, fields);
  const handle = sized.divider(), width = () => parseFloat(sized.host().style.width);
  assert.equal(handle.attributes.role, 'separator'); assert.equal(handle.attributes['aria-controls'], sized.host().id);
  assert.equal(handle.tabIndex, 0); assert.equal(width(), 480);
  sized.body.style.userSelect = 'text'; sized.body.style.cursor = 'auto';
  handle.fire('pointerdown', { clientX: 900 }); assert.equal(handle.captureId, 1);
  handle.fire('pointermove', { clientX: -1000, pointerId: 2 }); assert.equal(width(), 480);
  handle.fire('pointermove', { clientX: -1000 }); assert.equal(width(), 800);
  handle.fire('pointermove', { clientX: 2000 }); assert.equal(width(), 350);
  handle.fire('pointercancel'); assert.equal(handle.captureId, null);
  assert.equal(sized.body.style.userSelect, 'text'); assert.equal(sized.body.style.cursor, 'auto');
  handle.fire('keydown', { key: 'ArrowLeft' }); assert.equal(width(), 370);
  handle.fire('keydown', { key: 'End' }); assert.equal(width(), 800);
  sized.row.clientWidth = 1000; sized.resize(); assert.equal(width(), 630);
  const otherPanel = new Element(); otherPanel.rectWidth = 200; sized.row.append(otherPanel);
  sized.mutate([{ target: sized.row }]); assert.equal(width(), 430);
  otherPanel.rectWidth = 500; sized.resize(); assert.equal(handle.hidden, true);
  assert.equal(sized.host().style.position, 'fixed');
  otherPanel.remove(); sized.row.clientWidth = 1200; sized.resize(); assert.equal(width(), 430);
  handle.fire('keydown', { key: 'Home' }); assert.equal(width(), 350);
  handle.fire('pointerdown', { clientX: 900 });
  handle.fire('pointermove', { clientX: 650 }); handle.fire('pointerup'); assert.equal(width(), 600);
  handle.fire('pointerdown', { clientX: 650 });
  sized.window.innerWidth = 600; sized.window.fire('resize');
  assert.equal(handle.hidden, true); assert.equal(handle.captureId, null);
  assert.equal(sized.body.style.userSelect, 'text');
  sized.window.innerWidth = 1440; sized.window.fire('resize'); assert.equal(width(), 600);
  assert.deepEqual(ok(await sized.call()), draft);
  handle.fire('pointerdown', { clientX: 650 }); sized.q('close').fire('click');
  assert.equal(handle.captureId, null); assert.equal(sized.divider(), undefined);
  assert.equal(sized.sizeObservers.some(observer => observer.active), false);
  assert.deepEqual(ok(await sized.call()), draft); assert.equal(width(), 600);
  handle.fire('pointerdown', { clientX: 650 }); sized.location.pathname = '/c/third-chat'; sized.mutate();
  assert.equal(handle.captureId, null); assert.equal(sized.divider(), undefined);
  assert.equal(sized.body.style.userSelect, 'text'); assert.equal(sized.window.events.resize.length, 0);
  console.log('PASS complete initial draft, resize bounds/pointer/keyboard, container changes and cleanup without form changes');
  const lookup = environment();
  const snapshot = () => JSON.parse(JSON.stringify(lookup.window.__eesWODemoV1.view()));
  const equipmentRows = () => lookup.q('results').children.filter(node => node.dataset.equipmentId);
  let search = ok(await lookup.call('equipment', { site: '천안', line: '조립 1라인' }));
  const lookupHost = lookup.host();
  assert.equal(search.opened, true); assert.equal(search.screen, 'equipment');
  assert.equal(lookup.q('panel-title').textContent, '설비 조회');
  assert.equal(search.equipment_search.matches_count, 2);
  assert.deepEqual(equipmentRows().map(node => node.dataset.equipmentId), ['KR-CA-211', 'KR-CA-212']);
  assert.equal(lookup.q('site').value, '천안'); assert.equal(lookup.q('line').value, '조립 1라인');
  assert.equal(lookup.q('corporation').value, ''); assert.equal(lookup.q('shop').value, '');
  assert.equal(lookup.q('site').disabled, false); assert.equal(lookup.q('line').disabled, false);
  assert.equal(search.equipment_search.selected_equipment, null); assert.equal(search.equipment, null);
  assert.equal(lookup.q('form').hidden, true); assert.equal(lookup.q('back-to-wo').hidden, true);
  equipmentRows()[0].fire('click'); search = snapshot();
  assert.equal(search.equipment_search.selected_equipment.id, 'KR-CA-211');
  assert.equal(search.equipment, null); assert.equal(search.fields.title, '');
  assert.equal(lookup.q('form').hidden, true); assert.equal(lookup.q('search-hint').hidden, false);
  assert.ok(lookup.q('selected').textContent.includes('KR-CA-211'));
  lookup.q('query').value = '권취 '; lookup.q('query').fire('input');
  assert.equal(lookup.q('query').value, '권취 ');
  lookup.q('query').value += '설비'; lookup.q('query').fire('input');
  assert.equal(snapshot().equipment_search.filters.query, '권취 설비');
  assert.equal(snapshot().equipment_search.matches_count, 1);
  lookup.q('equipment-code').value = ' KR-CA-211 '; lookup.q('equipment-code').fire('input');
  assert.equal(lookup.q('equipment-code').value, ' KR-CA-211 ');
  assert.equal(snapshot().equipment_search.matches_count, 1);
  lookup.q('query').value = '없는 설비'; lookup.q('query').fire('input');
  assert.equal(snapshot().equipment_search.matches_count, 0);
  assert.equal(snapshot().equipment_search.selected_equipment, null);
  assert.ok(lookup.q('results').textContent.includes('조건에 맞는 설비가 없습니다'));
  search = ok(await lookup.call('equipment', { equipment_id: 'KR-CA-211', query: '조립 설비' }));
  assert.equal(search.equipment_search.matches_count, 0);
  assert.equal(lookup.q('equipment-code').value, 'KR-CA-211'); assert.equal(lookup.q('query').value, '조립 설비');
  search = ok(await lookup.call('equipment', { equipment_id: 'KR-CA' }));
  assert.equal(search.equipment_search.matches_count, 0);
  search = ok(await lookup.call('equipment', { site: '없는 사업장', equipment_id: 'KR-CA-211' }));
  assert.equal(search.equipment_search.matches_count, 0);
  assert.equal(lookup.q('site').value, '없는 사업장');
  assert.ok(lookup.q('site').children.some(option => option.value === '없는 사업장'));
  search = ok(await lookup.call('equipment', { equipment_id: 'KR-CA-211', query: '권취' }));
  assert.equal(search.equipment_search.matches_count, 1); assert.equal(search.equipment_search.selected_equipment, null);
  lookup.q('equipment-code').value = ''; lookup.q('equipment-code').fire('input');
  lookup.q('query').value = ''; lookup.q('query').fire('input');
  lookup.q('corporation').value = '한국'; lookup.q('corporation').fire('change');
  lookup.q('site').value = '천안'; lookup.q('site').fire('change');
  lookup.q('shop').value = '조립'; lookup.q('shop').fire('change');
  lookup.q('line').value = '조립 1라인'; lookup.q('line').fire('change');
  lookup.q('process').value = '권취'; lookup.q('process').fire('change');
  assert.equal(snapshot().equipment_search.matches_count, 1);
  lookup.q('site').value = '울산'; lookup.q('site').fire('change');
  assert.deepEqual(['shop', 'line', 'process'].map(key => snapshot().equipment_search.filters[key]), ['', '', '']);
  assert.equal(snapshot().equipment_search.matches_count, 8);
  assert.equal(lookup.host(), lookupHost);
  console.log('PASS equipment panel, parent-omitted filters, exact ID/query, zero/multiple results, manual search and detail selection without WO');

  search = ok(await lookup.call('equipment', { equipment_id: 'KR-CA-211' }));
  equipmentRows()[0].fire('click');
  let selectedView = ok(await lookup.call());
  assert.equal(selectedView.screen, 'wo');
  assert.equal(selectedView.equipment_search.selected_equipment.id, 'KR-CA-211');
  assert.equal(selectedView.equipment, null);
  selectedView = ok(await lookup.call('update', { equipment_id: selectedView.equipment_search.selected_equipment.id, ...fields }, selectedView.revision));
  assert.equal(selectedView.equipment.id, 'KR-CA-211'); assert.deepEqual(selectedView.fields, fields);
  assert.equal(lookup.q('form').hidden, false); assert.equal(lookup.host(), lookupHost);
  lookup.q('description').value = '직접 입력한 상세 증상'; lookup.q('description').fire('input');
  const beforeBrowse = snapshot();
  search = ok(await lookup.call('equipment', { site: '울산', line: '조립 1라인' }));
  equipmentRows()[0].fire('click');
  assert.equal(snapshot().equipment_search.selected_equipment.id, 'KR-US-211');
  for (const key of ['revision', 'phase', 'equipment', 'fields', 'filters']) assert.deepEqual(snapshot()[key], beforeBrowse[key]);
  assert.equal(lookup.q('form').hidden, true); assert.equal(lookup.q('back-to-wo').hidden, false);
  lookup.q('back-to-wo').fire('click');
  assert.equal(snapshot().screen, 'wo'); assert.equal(lookup.q('form').hidden, false);
  assert.equal(lookup.q('description').value, '직접 입력한 상세 증상');
  lookup.q('form').fire('submit'); const beforeReviewBrowse = snapshot();
  assert.equal(beforeReviewBrowse.phase, 'review');
  const reviewText = lookup.q('review-values').textContent;
  search = ok(await lookup.call('equipment', { equipment_id: 'US-111' }));
  equipmentRows()[0].fire('click');
  assert.equal(lookup.q('review').hidden, true); assert.equal(lookup.q('form').hidden, true);
  for (const key of ['revision', 'phase', 'equipment', 'fields', 'filters']) assert.deepEqual(snapshot()[key], beforeReviewBrowse[key]);
  lookup.q('back-to-wo').fire('click');
  assert.equal(lookup.q('review').hidden, false); assert.equal(lookup.q('review-values').textContent, reviewText);
  lookup.q('issue').fire('click'); const beforeIssuedBrowse = snapshot();
  assert.equal(beforeIssuedBrowse.phase, 'issued');
  const resultText = lookup.q('result-values').textContent;
  assert.ok(resultText.includes('KR-CA-211')); assert.ok(!resultText.includes('US-111'));
  search = ok(await lookup.call('equipment', { corporation: '헝가리' }));
  lookup.q('line').value = '전극 2라인'; lookup.q('line').fire('change');
  equipmentRows()[0].fire('click');
  for (const key of ['revision', 'phase', 'equipment', 'fields', 'filters']) assert.deepEqual(snapshot()[key], beforeIssuedBrowse[key]);
  lookup.q('back-to-wo').fire('click');
  assert.equal(lookup.q('result').hidden, false); assert.equal(lookup.q('result-values').textContent, resultText);
  lookup.q('browse-equipment').fire('click');
  assert.equal(snapshot().screen, 'equipment'); assert.equal(lookup.q('form').hidden, true);
  const selectedBeforeClose = snapshot().equipment_search;
  lookup.q('close').fire('click'); assert.equal(lookup.host(), undefined);
  assert.deepEqual(ok(await lookup.call()).equipment_search, selectedBeforeClose);
  assert.equal(lookup.host(), lookupHost);
  lookup.location.pathname = '/c/next-search'; lookup.mutate();
  search = ok(await lookup.call('equipment', { site: '천안' }, undefined, 'next-search'));
  assert.equal(search.equipment, null); assert.equal(search.equipment_search.selected_equipment, null);
  assert.notEqual(lookup.host(), lookupHost);
  bad(await unsupported.call('equipment', { site: '천안' }), 'unsupported_layout');
  lookup.location.pathname = '/';
  bad(await lookup.call('equipment', { site: '천안' }, undefined, 'next-search'), 'regular_chat_required');
  assert.equal(lookup.host(), undefined);
  console.log('PASS selected equipment to complete WO, existing manual/review/issued data preserved, return/close/reopen and lookup lifecycle errors');
  const retained = environment();
  const retainedView = () => JSON.parse(JSON.stringify(retained.window.__eesWODemoV1.view()));
  const navigate = (chat, { replace = true, event } = {}) => {
    retained.location.pathname = chat.startsWith('/') ? chat : '/c/' + chat;
    const previous = replace ? retained.replaceLayout() : null;
    if (event === 'popstate') retained.window.fire('popstate');
    else if (event === 'navigation') retained.window.navigation.fire('navigatesuccess');
    retained.flushMutations();
    return previous;
  };
  ok(await retained.call('equipment', { site: '천안', line: '조립 1라인' }));
  const retainedHost = retained.host(), retainedLauncher = retained.launcher();
  assert.equal(retainedLauncher.textContent, '업무 패널 닫기');
  assert.equal(retainedLauncher.attributes['aria-expanded'], 'true');
  assert.equal(retainedLauncher.attributes['aria-controls'], retainedHost.id);
  assert.equal(retained.column.style.position, 'relative');
  assert.ok(!retainedHost.children.includes(retainedLauncher));
  retained.q('results').children.find(node => node.dataset.equipmentId === 'KR-CA-211').fire('click');
  retained.q('query').value = '권취'; retained.q('query').fire('input');
  retained.divider().fire('keydown', { key: 'End' });
  const retainedSearch = retainedView();
  retained.flushMutations();
  assert.equal(retained.flushMutations(), 0);
  const firstColumn = navigate('unvisited').column;
  assert.equal(retained.host(), undefined); assert.equal(retained.launcher(), undefined);
  assert.equal(firstColumn.style.minWidth, ''); assert.equal(firstColumn.style.position, undefined);
  assert.equal(retained.window.__eesWODemoV1, undefined);
  assert.equal(retained.window.events.resize.length, 0);
  assert.equal(retained.sizeObservers.some(observer => observer.active), false);
  bad(await retained.call('view', {}, undefined, 'sample-chat'), 'regular_chat_required');
  navigate('sample-chat'); // No Tool call: the existing search and DOM return automatically.
  assert.equal(retained.host(), retainedHost); assert.equal(retained.launcher(), retainedLauncher);
  assert.deepEqual(retainedView(), retainedSearch);
  assert.equal(retained.host().style.width, '800px');
  assert.equal(retained.q('panel-title').textContent, '설비 조회');
  retainedLauncher.fire('click'); retained.flushMutations();
  assert.equal(retained.host(), undefined); assert.equal(retained.launcher(), retainedLauncher);
  assert.equal(retainedLauncher.textContent, '업무 패널 열기');
  assert.equal(retainedLauncher.attributes['aria-expanded'], 'false');
  assert.equal(retained.window.events.resize.length, 0);
  navigate('unvisited'); navigate('sample-chat');
  assert.equal(retained.host(), undefined); assert.equal(retained.launcher(), retainedLauncher);
  assert.equal(retainedLauncher.textContent, '업무 패널 열기');
  retainedLauncher.fire('click'); retained.flushMutations();
  assert.equal(retained.host(), retainedHost); assert.deepEqual(retainedView(), retainedSearch);
  retained.q('close').fire('click'); retainedLauncher.fire('click');
  assert.deepEqual(retainedView(), retainedSearch);
  assert.equal(retained.window.events.resize.length, 1);
  assert.equal(retained.observers.filter(observer => observer.active).length, 2);
  console.log('PASS retained search/selection/width, replaced anchors, direct toggle, closed preference and mutation quiescence');

  let retainedDraft = ok(await retained.call());
  retainedDraft = ok(await retained.call('update', { equipment_id: 'KR-CA-211', ...fields }, retainedDraft.revision));
  retained.q('description').value = '사용자가 직접 쓴 증상과 요청'; retained.q('description').fire('input');
  const manualDraft = retainedView();
  navigate('second-chat');
  const independent = ok(await retained.call('equipment', { site: '울산' }, undefined, 'second-chat'));
  const secondHost = retained.host(), secondLauncher = retained.launcher();
  assert.notEqual(secondHost, retainedHost); assert.notEqual(secondLauncher, retainedLauncher);
  assert.equal(independent.fields.description, '');
  retained.q('results').children.find(node => node.dataset.equipmentId).fire('click');
  const secondState = retainedView();
  bad(await retained.call('update', { description: 'late edit from another chat' }, manualDraft.revision, 'sample-chat'), 'regular_chat_required');
  assert.equal(retained.host(), secondHost); assert.deepEqual(retainedView(), secondState);
  navigate('sample-chat');
  assert.deepEqual(retainedView(), manualDraft);
  assert.equal(retained.q('description').value, manualDraft.fields.description);
  retained.q('form').fire('submit');
  const reviewedDraft = retainedView(), retainedReviewText = retained.q('review-values').textContent;
  navigate('second-chat'); assert.equal(retained.host(), secondHost); assert.deepEqual(retainedView(), secondState);
  navigate('sample-chat');
  assert.deepEqual(retainedView(), reviewedDraft); assert.equal(retained.q('review').hidden, false);
  assert.equal(retained.q('review-values').textContent, retainedReviewText);
  retained.q('issue').fire('click');
  const issuedDraft = retainedView(), retainedIssueText = retained.q('result-values').textContent;
  navigate('second-chat'); navigate('sample-chat');
  assert.deepEqual(retainedView(), issuedDraft); assert.equal(retained.q('result').hidden, false);
  assert.equal(retained.q('result-values').textContent, retainedIssueText);
  assert.equal(retained.q('result-number').textContent, 'WO-DEMO-0001');
  retained.q('issue').fire('click'); assert.deepEqual(retainedView(), issuedDraft);
  assert.equal(retained.window.events.resize.length, 1);
  assert.equal(retained.sizeObservers.filter(observer => observer.active).length, 1);
  console.log('PASS chat isolation, delayed responses, manual draft/review/issued restoration and no duplicate global listeners');

  navigate('second-chat', { replace: false, event: 'popstate' });
  assert.equal(retained.host(), secondHost);
  navigate('sample-chat', { replace: false, event: 'navigation' });
  assert.equal(retained.host(), retainedHost); assert.deepEqual(retainedView(), issuedDraft);
  navigate('/', { event: 'popstate' });
  assert.equal(retained.host(), undefined); assert.equal(retained.launcher(), undefined);
  assert.ok(retained.window.__eesWODemoManagerV1);
  navigate('sample-chat'); assert.deepEqual(retainedView(), issuedDraft);
  retained.divider().fire('pointerdown', { clientX: 700 });
  navigate('/auth', { event: 'popstate' });
  assert.equal(retained.host(), undefined); assert.equal(retained.launcher(), undefined);
  assert.equal(retained.window.__eesWODemoManagerV1, undefined);
  assert.equal(retained.window.__eesWODemoV1, undefined);
  for (const event of ['resize', 'popstate', 'pagehide']) assert.equal(retained.window.events[event].length, 0);
  assert.equal(retained.window.navigation.events.navigatesuccess.length, 0);
  assert.equal(retained.observers.some(observer => observer.active), false);
  assert.equal(retained.sizeObservers.some(observer => observer.active), false);
  navigate('sample-chat'); assert.equal(retained.host(), undefined); assert.equal(retained.launcher(), undefined);
  const afterAuth = ok(await retained.call());
  assert.equal(afterAuth.equipment, null); assert.equal(afterAuth.fields.description, '');
  retained.window.fire('pagehide');
  assert.equal(retained.window.__eesWODemoManagerV1, undefined);
  assert.equal(retained.host(), undefined); assert.equal(retained.launcher(), undefined);
  assert.equal(retained.observers.some(observer => observer.active), false);
  const noNavigationAPI = environment({ navigation: false });
  ok(await noNavigationAPI.call()); const fallbackHost = noNavigationAPI.host();
  noNavigationAPI.location.pathname = '/c/another-chat'; noNavigationAPI.replaceLayout(); noNavigationAPI.flushMutations();
  assert.equal(noNavigationAPI.host(), undefined);
  noNavigationAPI.location.pathname = '/c/sample-chat'; noNavigationAPI.replaceLayout(); noNavigationAPI.flushMutations();
  assert.equal(noNavigationAPI.host(), fallbackHost);
  console.log('PASS SPA navigation events, new-chat entry, auth/pagehide cleanup and MutationObserver fallback');
  console.log('10 grouped JS state checks passed (synthetic DOM; browser rendering unverified).');
})().catch(error => { console.error(error); process.exitCode = 1; });
