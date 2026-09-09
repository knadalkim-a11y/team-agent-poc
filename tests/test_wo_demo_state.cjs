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
  set textContent(value) { this._text = String(value); this.replaceChildren(); }
  get textContent() { return (this._text || '') + this.children.map(c => c.textContent).join(''); }
  append(...nodes) { nodes.forEach(node => { node.remove(); node.parentElement = this; this.children.push(node); }); }
  replaceChildren(...nodes) { [...this.children].forEach(node => node.remove()); this.append(...nodes); }
  remove() { if (this.parentElement) this.parentElement.children = this.parentElement.children.filter(c => c !== this); this.parentElement = null; }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  addEventListener(type, callback) { (this.events[type] ||= []).push(callback); }
  removeEventListener(type, callback) { this.events[type] = (this.events[type] || []).filter(c => c !== callback); }
  fire(type) { (this.events[type] || []).forEach(callback => callback({ target: this, preventDefault() {} })); }
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
function environment({ layout = true } = {}) {
  const body = new Element('body'); body.connected = true;
  const row = new Element(), column = new Element(), anchor = new Element();
  body.append(row); row.append(column); column.append(anchor);
  const documentElement = new Element('html'), observers = [], window = new Element('window');
  window.innerWidth = 1440;
  const document = { body, documentElement, createElement: tag => new Element(tag), querySelector: selector => layout && selector === '#chat-container #chat-pane' ? anchor : null };
  class MutationObserver {
    constructor(callback) { this.callback = callback; observers.push(this); }
    observe() { this.active = true; }
    disconnect() { this.active = false; }
  }
  const location = { pathname: '/c/sample-chat' };
  const context = vm.createContext({ window, document, location, MutationObserver, getComputedStyle: () => ({ display: 'flex' }) });
  const host = () => row.children.find(node => node.id === 'ees-wo-demo-panel');
  const q = id => host()?.shadowRoot.getElementById(id);
  async function call(action = 'view', changes = {}, revision, chat_id = 'sample-chat') {
    const payload = capture({ action, changes, revision, chat_id });
    const result = await vm.runInContext('(async () => {\n' + payload.code + '\n})()', context);
    return JSON.parse(JSON.stringify(result));
  }
  return { window, location, row, host, q, call, mutate: () => observers.filter(o => o.active).forEach(o => o.callback()), context };
}
const ok = result => { assert.equal(result.ok, true, JSON.stringify(result)); assert.equal(result.demo, true); return result; };
const bad = (result, code) => { assert.equal(result.ok, false); if (code) assert.equal(result.error.code, code); return result; };

(async () => {
  const env = environment(); let state = ok(await env.call());
  assert.equal(state.matches_count, 32); assert.equal(state.matches.length, 8);
  const firstHost = env.host(); assert.ok(firstHost); assert.equal(env.row.children.length, 2);
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
  console.log('PASS close/reopen, changed-chat reset and unsupported routes/layout');
  console.log('4 grouped JS state checks passed (synthetic DOM; browser rendering unverified).');
})().catch(error => { console.error(error); process.exitCode = 1; });
