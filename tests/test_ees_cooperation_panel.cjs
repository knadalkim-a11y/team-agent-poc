/* Actual production script + synthetic DOM contracts. Not a browser rendering
 * or an internal WebUI/LLM acceptance test. Run: node tests/test_ees_cooperation_panel.cjs */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {spawnSync} = require('node:child_process');
const root = path.resolve(__dirname, '..');
const workScript = fs.readFileSync(path.join(root, 'agent-pack/skills/cross-system-analysis/ui/work-panel.js'), 'utf8');
const script = fs.readFileSync(path.join(root, 'agent-pack/skills/cross-system-analysis/ui/cooperation-panel.js'), 'utf8');
class Element {
  constructor(tag = 'div') {
    this.tagName = tag; this.children = []; this.parentElement = null; this.style = {minWidth: ''};
    this.dataset = {}; this.attributes = {}; this.events = {}; this.hidden = false; this.value = ''; this.scrollTop = 0;
    const classes = new Set(); this.classList = {contains: key => classes.has(key), toggle: (key, on) => on ? classes.add(key) : classes.delete(key)};
  }
  get isConnected() { return Boolean(this.connected || this.parentElement?.isConnected); }
  set textContent(value) { this._text = String(value); this.replaceChildren(); this.mutation(); }
  get textContent() { return (this._text || '') + this.children.map(child => child.textContent).join(''); }
  mutation() { if (this.isConnected) { let root = this; while (root.parentElement) root = root.parentElement; root.onMutation?.({target: this}); } }
  append(...nodes) { nodes.forEach(node => { node.remove(); node.parentElement = this; this.children.push(node); this.mutation(); }); }
  insertBefore(node, reference) { if (!reference) return this.append(node); const i = this.children.indexOf(reference); assert.notEqual(i, -1); node.remove(); node.parentElement = this; this.children.splice(i, 0, node); this.mutation(); }
  replaceChildren(...nodes) { [...this.children].forEach(node => node.remove()); this.append(...nodes); }
  remove() { const parent = this.parentElement; if (parent) parent.children = parent.children.filter(node => node !== this); this.parentElement = null; parent?.mutation(); }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  getBoundingClientRect() { return {width: this.rectWidth ?? (parseFloat(this.style.width) || this.clientWidth || 0)}; }
  setPointerCapture(id) { this.captureId = id; }
  hasPointerCapture(id) { return this.captureId === id; }
  releasePointerCapture(id) { if (this.captureId === id) this.captureId = null; }
  addEventListener(type, handler) { (this.events[type] ||= []).push(handler); }
  removeEventListener(type, handler) { this.events[type] = (this.events[type] || []).filter(item => item !== handler); }
  fire(type, changes = {}) { (this.events[type] || []).forEach(handler => handler({target: this, button: 0, pointerId: 1, preventDefault() {}, ...changes})); }
  click() { this.fire('click'); }
  focus() { this.focused = true; let root = this; while (root.parentElement) root = root.parentElement; root.activeElement = this; }
  attachShadow() { this.shadowRoot = new Shadow(); return this.shadowRoot; }
  querySelector(selector) {
    const match = selector.match(/^\[data-focus-key="([^"]+)"\]$/);
    return descendants(this).find(node => match ? node.dataset.focusKey === match[1] : node.tagName === selector) || null;
  }
  compareDocumentPosition(other) { return this.order < other.order ? 4 : this.order > other.order ? 2 : 0; }
}
const descendants = node => node.children.flatMap(child => [child, ...descendants(child)]);
class Shadow extends Element {
  set innerHTML(html) {
    this.ids = new Map(); this.origins = new Map();
    // Only fixed template IDs/attributes are parsed. All data nodes are real
    // production createElement/textContent operations exercised below.
    for (const match of html.matchAll(/<([a-z][\w-]*)\b([^<>]*)>/gi)) {
      const attrs = Object.fromEntries([...match[2].matchAll(/([\w-]+)="([^"]*)"/g)].map(item => [item[1], item[2]]));
      if (!attrs.id && !attrs['data-origin-for']) continue;
      const node = new Element(match[1]); node.id = attrs.id; node.hidden = /\bhidden\b/.test(match[2]);
      if (attrs.id) this.ids.set(attrs.id, node);
      if (attrs['data-origin-for']) this.origins.set(attrs['data-origin-for'], node);
      this.append(node);
    }
  }
  getElementById(id) { return this.ids.get(id) || null; }
  querySelector(selector) { const origin = selector.match(/^\[data-origin-for="([^"]+)"\]$/); return origin ? this.origins.get(origin[1]) || null : super.querySelector(selector); }
}
function environment({supported = true} = {}) {
  const body = new Element('body'); body.connected = true;
  let row, column, anchor, toolbar, controls, navbar;
  const observers = [], resizeObservers = [], mutations = [], messageNodes = new Map();
  const window = new Element('window'); window.innerWidth = 1440; window.navigation = new Element('navigation');
  const documentElement = new Element('html'), location = {pathname: '/c/chat-a'};
  const replaceNavbar = () => {
    navbar?.remove(); navbar = new Element('nav'); toolbar = new Element(); const wrapper = new Element(); controls = new Element('button'); controls.setAttribute('aria-label', 'Controls'); wrapper.append(controls); toolbar.append(wrapper); navbar.append(toolbar); column.insertBefore(navbar, anchor);
    column.querySelector = selector => selector === 'nav button[aria-label="Controls"]' ? controls : selector === 'nav .flex-none.items-center.gap-2.self-center' ? toolbar : null;
  };
  const replaceLayout = () => {
    row?.remove(); row = new Element(); column = new Element(); anchor = new Element(); row.clientWidth = 1200;
    body.append(row); row.append(column); column.append(anchor); replaceNavbar();
  };
  replaceLayout(); body.onMutation = record => mutations.push(record);
  const document = {body, documentElement, createElement: tag => new Element(tag), createElementNS: (_ns, tag) => new Element(tag), getElementById: id => descendants(body).find(node => node.id === id) || messageNodes.get(id) || null,
    querySelector: selector => supported && selector === '#chat-container #chat-pane' ? anchor : null};
  class MutationObserver { constructor(callback) { this.callback = callback; observers.push(this); } observe(target) { this.target = target; this.active = true; } disconnect() { this.active = false; } }
  class ResizeObserver { constructor(callback) { this.callback = callback; this.targets = new Set(); resizeObservers.push(this); } observe(target) { this.active = true; this.targets.add(target); } disconnect() { this.active = false; this.targets.clear(); } }
  const context = vm.createContext({window, document, location, MutationObserver, ResizeObserver, getComputedStyle: node => ({display: 'flex', position: node.style.position || 'static'})});
  const host = () => document.getElementById('ees-cooperation-panel'), q = id => host()?.shadowRoot.getElementById(id);
  const run = async code => JSON.parse(JSON.stringify(await vm.runInContext('(async () => {\n' + code + '\n})()', context)));
  const call = event => run('const eesPanelUpdate=' + JSON.stringify(event) + ';\n' + workScript + '\n' + script);
  const mutate = () => { const records = mutations.splice(0); observers.filter(observer => observer.active && observer.target === body).forEach(observer => observer.callback(records)); };
  const flush = () => { let count = 0; while (mutations.length) { assert.ok(++count <= 10, 'Own mutations must settle, with no panel-manager loop'); mutate(); } return count; };
  return {window, body, document, documentElement, location, context, observers, resizeObservers, messageNodes, host, q, call, run, mutate, flush, replaceNavbar, replaceLayout,
    get row() { return row; }, get column() { return column; }, get toolbar() { return toolbar; }, get controls() { return controls; },
    launcher: () => document.getElementById('ees-work-panel-toggle'), divider: () => document.getElementById('ees-cooperation-resizer'),
    resize: () => resizeObservers.filter(observer => observer.active).forEach(observer => observer.callback()),
    cards: () => descendants(q('batches')).filter(node => node.dataset.callId),
    comparisons: () => q('comparisons').children,
    route: pathname => { location.pathname = pathname; mutate(); },
  };
}
const event = (changes = {}) => ({version: 1, kind: 'specialist', chat_id: 'chat-a', message_id: 'message-a', call_id: 'call-ems', batch_id: 'batch-a', seq: 1, phase: 'requested', system: 'EMS', request: {question: '정비 이력을 확인해 주세요.', kind: 'initial'}, queries: [], analysis: '', analysis_truncated: false, error: null, ...changes});
const ok = value => { assert.equal(value.ok, true, JSON.stringify(value)); return value; };
const bad = (value, code) => { assert.equal(value.ok, false); assert.equal(value.error.code, code); };

(async () => {
  const env = environment(); ok(await env.call(event()));
  assert.equal(env.cards().length, 1); assert.match(env.q('detail-body').textContent, /정비 이력을/); assert.match(env.cards()[0].textContent, /요청 전달 중/);
  const firstHost = env.host(); assert.equal(env.launcher().attributes['aria-expanded'], 'true');
  ok(await env.call(event({system: 'APC', call_id: 'call-apc', phase: 'analyzing'})));
  ok(await env.call(event({system: 'FDC', call_id: 'call-fdc'})));
  assert.equal(env.cards().length, 3); assert.match(env.q('batches').textContent, /병렬 분석 요청/);
  assert.equal(env.host(), firstHost); assert.equal(env.row.children.length, 3); env.flush();
  assert.equal(ok(await env.call(event())).updated, false);
  ok(await env.call(event({seq: 4, phase: 'completed', analysis: '정비 내역에서 사건 A를 확인했습니다.'})));
  assert.equal(ok(await env.call(event({seq: 3, phase: 'querying'}))).updated, false);
  assert.match(env.cards()[0].textContent, /완료/);
  assert.equal(ok(await env.call(event({seq: 5, system: 'APC'}))).updated, false);
  console.log('PASS actual selected cards, parallel batch, mounted once, stale snapshots and identity protection');

  env.cards()[1].click(); env.cards()[1].focus(); env.q('scroll').scrollTop = 234;
  ok(await env.call(event({seq: 5, analysis: '다른 전문 회신', phase: 'completed'})));
  assert.equal(env.q('detail-title').textContent, 'APC Assistant'); assert.equal(env.cards()[1].focused, true); assert.equal(env.q('scroll').scrollTop, 234);
  const injection = '</script><img src=x onerror=globalThis.EES_INJECTION=true> ` ${bad}';
  ok(await env.call(event({call_id: 'call-apc', system: 'APC', seq: 2, phase: 'querying', request: {question: injection, kind: 'initial'}, queries: [{index: 1, tool: 'query_demo_data', arguments: {dataset: 'sample_a', equipment_id: 'EQ-01'}, status: 'completed', record_count: 0, event_ids: []}]})));
  assert.ok(env.q('detail-body').textContent.includes(injection)); assert.match(env.q('detail-body').textContent, /조회 결과 0건/); assert.equal(env.context.EES_INJECTION, undefined);
  ok(await env.call(event({call_id: 'call-apc', system: 'APC', seq: 3, phase: 'partial', analysis: '실제 회신 '.repeat(1000), analysis_truncated: true})));
  assert.match(env.q('detail-body').textContent, /16,000자/); assert.match(env.q('detail-body').textContent, /일부 회신 또는 근거/);
  const expand = env.q('detail-body').querySelector('[data-focus-key="expand"]'); expand.click();
  assert.equal(env.q('detail-body').querySelector('[data-focus-key="expand"]').attributes['aria-expanded'], 'true');
  ok(await env.call(event({call_id: 'call-fdc', system: 'FDC', seq: 2, phase: 'failed', error: 'access_denied'})));
  assert.equal(env.q('detail-body').querySelector('[data-focus-key="expand"]').attributes['aria-expanded'], 'true');
  env.cards()[2].click(); assert.match(env.q('detail-body').textContent, /완료하지 못했습니다/); assert.doesNotMatch(env.q('detail-body').textContent, /access_denied/);
  ok(await env.call(event({call_id: 'call-ems-followup', batch_id: 'batch-b', request: {kind: 'followup', question: '사건 A의 상세 기록을 확인해 주세요.'}})));
  assert.match(env.q('batches').textContent, /보완 분석/); assert.equal(env.cards().length, 4);
  console.log('PASS preserved selection/focus/scroll, safe exact text, zero records, partial/truncated replies and followup');

  const comparison = event({kind: 'comparison', system: undefined, call_id: 'compare-a', batch_id: 'compare-a', arguments: {dataset: 'sample_b', group_by: 'equipment_id'}, phase: 'requested'});
  ok(await env.call(comparison)); env.comparisons()[0].click(); assert.match(env.q('synthesis').textContent, /交|교차 비교/);
  const group = {total_events: 2, confirmed_events: 0, mean_confirmed_minutes: null, mean_denominator: 0, not_confirmed_events: 1, unassessable_events: 1};
  ok(await env.call({...comparison, seq: 2, phase: 'completed', result: {ok: true, summary: group, calculation: {conditions: 'APC와 FDC 동시 허용 범위', consecutive_samples: 5, end: '5번째 표본 - 생산 재개', missing_policy: '누락 표본은 0으로 치환하지 않음'}, comparisons: [{conditions: {equipment_id: 'EQ-02'}, groups: {planned_start: group, maintenance: group}, maintenance_minus_planned_minutes: null}], events: [{event_id: 'B-01', equipment_id: 'EQ-02', recipe_id: 'R-01', resumed_at: '2026-09-10T09:00:00', state: 'unassessable', confirmed_after_minutes: null, missing_samples: {APC: 1, FDC: 0}, evidence_record_ids: ['EMS-B-01']}], message: '합성 관측치입니다.'}}));
  assert.match(env.q('detail-body').textContent, /계산 불가/); assert.doesNotMatch(env.q('detail-body').textContent, /0분/); assert.match(env.q('detail-body').textContent, /평균 분모0건/); assert.match(env.q('detail-body').textContent, /누락 표본: APC 1, FDC 0/);
  let details = env.q('detail-body').querySelector('[data-focus-key="evidence"]').parentElement; details.open = true; details.fire('toggle'); details.querySelector('summary').focus();
  ok(await env.call(event({call_id: 'call-ems-followup', batch_id: 'batch-b', seq: 2, phase: 'cancelled'})));
  details = env.q('detail-body').querySelector('[data-focus-key="evidence"]').parentElement; assert.equal(details.open, true); assert.equal(details.querySelector('summary').focused, true);
  assert.equal(env.q('detail-body').querySelector('[data-focus-key="criteria"]').parentElement.open, false);
  assert.equal(descendants(env.q('detail-body')).filter(node => node.className === 'metric').length, 4);
  console.log('PASS actual comparison metrics, null is not zero, denominators/missing evidence and expanded evidence retention');

  const readableEnv = environment(), longQuestion = '사건 조건을 확인해 주세요. '.repeat(20) + injection;
  const formattedReply = ['## 핵심 확인', '', '- **생산 재개** 후 12분을 확인했습니다.', '- 근거 `EMS-A-01`을 사용했습니다.', '', '**한계·추가 확인**', '', '반복 정비를 원인으로 확정할 수 없습니다.', '두 번째 문장은 같은 문단입니다.', '', '2. 비교할 조건을 확인합니다.', '4. 누락 표본을 점검합니다.', '', '```text', injection, '```', '', injection].join('\n');
  const readableEvent = event({phase: 'completed', request: {question: longQuestion, kind: 'initial'}, analysis: formattedReply, queries: [{index: 1, arguments: {dataset: 'sample_a'}, status: 'completed', record_count: 1, event_ids: ['A-01']}]});
  ok(await readableEnv.call(readableEvent));
  const all = () => descendants(readableEnv.q('detail-body'));
  const disclosure = key => readableEnv.q('detail-body').querySelector('[data-focus-key="' + key + '"]').parentElement;
  assert.equal(disclosure('question').open, false); assert.equal(disclosure('queries').open, false);
  assert.ok(disclosure('question').textContent.includes(longQuestion));
  assert.match(disclosure('queries').textContent, /조립 2라인 · 기본 시연/); assert.doesNotMatch(disclosure('queries').textContent, /sample_a/);
  assert.deepEqual(all().filter(node => node.tagName === 'h4').map(node => node.textContent), ['핵심 확인', '한계·추가 확인']);
  assert.equal(all().find(node => node.tagName === 'strong').textContent, '생산 재개');
  assert.equal(all().find(node => node.tagName === 'code').textContent, 'EMS-A-01');
  assert.equal(all().filter(node => node.tagName === 'li').length, 4);
  assert.equal(all().find(node => node.tagName === 'ol').attributes.start, '2');
  assert.deepEqual(all().filter(node => node.tagName === 'li' && node.parentElement.tagName === 'ol').map(node => node.attributes.value), ['2', '4']);
  assert.equal(all().find(node => node.tagName === 'pre').textContent, injection);
  assert.ok(all().some(node => node.tagName === 'p' && node.textContent.includes('반복 정비를 원인으로 확정할 수 없습니다.\n두 번째 문장')));
  assert.equal(all().some(node => ['img', 'script', 'a'].includes(node.tagName)), false); assert.equal(readableEnv.context.EES_INJECTION, undefined);
  assert.ok(readableEnv.q('detail-body').textContent.indexOf('전문가 회신') < readableEnv.q('detail-body').textContent.indexOf('조회 근거'));
  // Native toggle may still be queued when a different specialist updates.
  const oldQuestion = disclosure('question'), oldQueries = disclosure('queries');
  oldQuestion.open = true; oldQueries.open = true; oldQueries.querySelector('summary').focus();
  readableEnv.q('scroll').scrollTop = 340;
  ok(await readableEnv.call(event({system: 'FDC', call_id: 'readability-other', phase: 'requested'})));
  assert.equal(disclosure('question').open, true); assert.equal(disclosure('queries').open, true); assert.equal(disclosure('queries').querySelector('summary').focused, true); assert.equal(readableEnv.q('scroll').scrollTop, 340);
  disclosure('question').open = false; disclosure('question').fire('toggle');
  oldQuestion.fire('toggle'); oldQueries.fire('toggle');
  ok(await readableEnv.call(event({system: 'FDC', call_id: 'readability-other', phase: 'completed', seq: 2})));
  assert.equal(disclosure('question').open, false); assert.equal(disclosure('queries').open, true);
  console.log('PASS readable exact reply blocks, safe formatting, reply-first detail, collapsed questions/queries and retained disclosure focus');

  ok(await env.call(event({message_id: 'message-b', call_id: 'new-question', batch_id: 'batch-new', request: {question: '이번 질문입니다.', kind: 'initial'}})));
  assert.match(env.q('detail-body').textContent, /이번 질문/); assert.equal(env.q('history').hidden, false);
  ok(await env.call(event({seq: 6, phase: 'completed', analysis: '늦게 도착한 이전 회신'})));
  assert.match(env.q('detail-body').textContent, /이번 질문/);
  const older = new Element(), newer = new Element(); older.order = 1; newer.order = 2;
  env.messageNodes.set('message-older-unseen', older); env.messageNodes.set('message-message-b', newer);
  ok(await env.call(event({message_id: 'older-unseen', call_id: 'older-call', batch_id: 'older-batch'})));
  assert.match(env.q('detail-body').textContent, /이번 질문/);
  env.q('message-select').value = 'message-a'; env.q('message-select').fire('change');
  ok(await env.call(event({message_id: 'message-b', call_id: 'new-question', batch_id: 'batch-new', seq: 2, phase: 'analyzing'})));
  assert.equal(env.q('message-select').value, 'message-a');
  env.route('/c/chat-b'); assert.equal(env.host(), null);
  ok(await env.call(event({chat_id: 'chat-b', message_id: 'b', call_id: 'b'})));
  const secondHost = env.host(); bad(await env.call(event({seq: 7, phase: 'completed', analysis: '이전 대화로만 보내기'})), 'inactive_chat'); assert.equal(env.host(), secondHost);
  env.route('/c/chat-a'); assert.equal(env.host(), firstHost);
  env.q('message-select').value = 'message-b'; env.q('message-select').fire('change'); assert.match(env.cards()[0].textContent, /최신 상태 미확인/); assert.match(env.q('live').textContent, /진행 알림이 중단/);
  ok(await env.call(event({message_id: 'message-b', call_id: 'new-question', batch_id: 'batch-new', seq: 3, phase: 'completed', analysis: '새로 확인된 회신'})));
  assert.match(env.cards()[0].textContent, /완료/); assert.doesNotMatch(env.q('live').textContent, /중단/);
  console.log('PASS per-message and per-chat isolation, delayed old events, selected history, route-return stale state');

  env.q('close').click(); assert.equal(env.host(), null); const closedLauncher = env.launcher();
  ok(await env.call(event({message_id: 'message-b', call_id: 'new-question', batch_id: 'batch-new', seq: 4, phase: 'completed'})));
  assert.equal(env.host(), null); assert.equal(env.launcher(), closedLauncher); env.launcher().click(); assert.equal(env.host(), firstHost);
  const wo = new Element('aside'); wo.id = 'ees-wo-demo-panel'; const woShadow = wo.attachShadow(); woShadow.ids = new Map(); const close = new Element('button'); woShadow.ids.set('close', close);
  const draft = {description: '작성 중인 WO 입력', revision: 15}; let closeCount = 0; close.addEventListener('click', () => { closeCount++; wo.remove(); });
  env.row.append(wo); env.flush(); assert.equal(env.host(), null); assert.equal(wo.isConnected, true);
  ok(await env.call(event({message_id: 'message-b', call_id: 'new-question', batch_id: 'batch-new', seq: 5, phase: 'completed'}))); assert.equal(env.host(), null); assert.equal(closeCount, 0);
  env.launcher().click(); assert.equal(closeCount, 1); assert.equal(wo.isConnected, false); assert.equal(env.host(), firstHost); assert.deepEqual(draft, {description: '작성 중인 WO 입력', revision: 15}); env.flush();
  env.row.append(wo); env.flush(); assert.equal(env.host(), null);
  ok(await env.call(event({message_id: 'message-c', call_id: 'c', batch_id: 'c'})));
  assert.equal(closeCount, 2); assert.equal(env.host(), firstHost); assert.equal(wo.isConnected, false); env.flush();
  env.replaceNavbar(); env.flush(); assert.equal(env.host(), firstHost); assert.ok(env.launcher().isConnected); assert.ok(env.controls.isConnected);
  env.replaceLayout(); env.flush(); assert.equal(env.host(), firstHost); assert.equal(env.row.children.length, 3);
  const native = new Element(); native.rectWidth = 500; env.row.append(native); env.flush();
  assert.equal(env.host().style.position, 'fixed'); assert.ok(env.resizeObservers.some(observer => observer.active && observer.targets.has(native)));
  native.rectWidth = 100; env.resize(); assert.equal(env.host().style.position, 'relative'); native.remove(); env.flush();
  console.log('PASS intentional collapse, WO mutual exclusion without draft mutation, native navbar/layout remount and settled observers');

  const width = () => parseFloat(env.host().style.width); assert.equal(width(), 480);
  env.divider().fire('keydown', {key: 'ArrowLeft'}); assert.equal(width(), 500);
  env.body.style.userSelect = 'text'; env.body.style.cursor = 'auto';
  env.divider().fire('pointerdown', {clientX: 800}); env.divider().fire('pointermove', {clientX: -1000, pointerId: 2}); assert.equal(width(), 500);
  env.divider().fire('pointermove', {clientX: -1000}); assert.equal(width(), 800);
  env.divider().fire('pointercancel'); assert.equal(env.body.style.userSelect, 'text'); assert.equal(env.body.style.cursor, 'auto');
  env.row.clientWidth = 720; env.resize(); assert.equal(width(), 350);
  env.window.innerWidth = 600; env.resize(); assert.equal(env.host().style.position, 'fixed'); assert.equal(env.divider().hidden, true);
  env.q('close').click(); env.launcher().click(); assert.equal(env.q('close').focused, true);
  env.host().shadowRoot.fire('keydown', {key: 'Escape'}); assert.equal(env.host(), null); assert.equal(env.launcher().focused, true);
  env.launcher().click(); env.documentElement.classList.toggle('dark', true); env.observers.filter(observer => observer.active && observer.target === env.documentElement).forEach(observer => observer.callback()); assert.equal(env.host().style.colorScheme, 'dark');
  env.route('/auth'); assert.equal(env.window.__eesCooperationV1, undefined); assert.equal(env.host(), null); assert.ok(env.observers.every(observer => !observer.active));
  const page = environment(); ok(await page.call(event())); page.window.fire('pagehide'); assert.equal(page.window.__eesCooperationV1, undefined);
  const failed = environment(); ok(await failed.call(event({phase: 'failed'}))); assert.match(failed.q('synthesis').textContent, /전문 분석이 종료/); assert.doesNotMatch(failed.q('synthesis').textContent, /기다리고/);
  ok(await failed.call(event({seq: 2, phase: 'partial', analysis: ''}))); assert.match(failed.q('synthesis').textContent, /전문 분석이 종료/); assert.doesNotMatch(failed.q('synthesis').textContent, /받았습니다/);
  ok(await failed.call(event({seq: 3, phase: 'cancelled', analysis: '취소 전에 확보한 회신'}))); assert.match(failed.q('synthesis').textContent, /작성한 내용을 받았습니다/); assert.doesNotMatch(failed.q('synthesis').textContent, /회신이 없습니다/);
  bad(await environment({supported: false}).call(event()), 'unsupported_layout'); bad(await environment().call(event({system: 'EGIS'})), 'invalid_panel_event');
  console.log('PASS width boundaries, pointer cleanup, narrow explicit focus/Escape, theme, logout/pagehide cleanup and unsupported layout');

  const planned = environment();
  const steps = [
    {id: 'maintenance', type: 'specialist', title: '정비 이력 확인', system: 'EMS', depends_on: [], reason_before: '정비 이후의 변화를 확인하기 위해 정비 이력을 먼저 조회합니다.', status: 'pending', result_summary: '', judgment_after: '', uncertainty: '', call_ids: []},
    {id: 'compare', type: 'comparison', title: '조건별 비교', system: 'EES', depends_on: ['maintenance'], reason_before: '같은 조건의 계획 기동과 정비 후 재개를 비교합니다.', status: 'pending', result_summary: '', judgment_after: '', uncertainty: '', call_ids: []},
    {id: 'finish', type: 'synthesis', title: '개선 기회 정리', system: 'EES', depends_on: ['compare'], reason_before: '확보한 자료의 범위 안에서 다음 행동을 정합니다.', status: 'pending', result_summary: '', judgment_after: '', uncertainty: '', call_ids: []},
  ];
  const planEvent = event({kind: 'plan', system: undefined, call_id: 'plan-one', batch_id: 'plan-one', plan_id: 'plan-one', phase: 'planned', title: '조립 2라인 개선 기회', steps, conclusion: '', next_action: '', limitations: '', changes: []});
  ok(await planned.call(planEvent));
  assert.equal(planned.q('summary-screen').hidden, true); assert.equal(planned.q('plan-screen').hidden, false);
  assert.match(planned.q('summary-conclusion').textContent, /실행 계획을 준비했습니다/);
  assert.equal(planned.q('step-list').children.length, 3); assert.equal(planned.q('summary-charts').children.length, 0);
  assert.equal(descendants(planned.body).filter(node => node.id === 'ees-work-panel-toggle').length, 1);
  assert.equal(planned.q('work-equipment').disabled, true); assert.equal(planned.q('work-wo').disabled, true);
  assert.doesNotMatch(planned.host().shadowRoot.textContent, /진행 시연/);
  planned.q('view-plan').click(); planned.q('step-list').children[1].click(); planned.q('detail-rationale-tab').click();
  assert.equal(planned.q('detail-rationale').hidden, false); assert.equal(planned.q('detail-body').hidden, true);
  assert.match(planned.q('detail-rationale').textContent, /실행 전 · 이 단계를 선택한 이유/);
  assert.match(planned.q('detail-rationale').textContent, /같은 조건의 계획 기동/);
  assert.match(planned.q('detail-rationale').textContent, /아직 실행 후 판단이 기록되지/);
  const completedSteps = steps.map(step => ({...step, status: 'completed'}));
  completedSteps[0] = {...completedSteps[0], call_ids: ['planned-specialist'], result_summary: '정비 이후 기록을 확보했습니다.', judgment_after: '정비 기록만으로 원인을 확정할 수 없습니다.', uncertainty: '운전 조건의 영향은 추가 확인이 필요합니다.'};
  completedSteps[1] = {...completedSteps[1], call_ids: ['planned-compare'], result_summary: '같은 설비에서 정비 후 재개의 확인 시간이 더 길었습니다.', judgment_after: '계산된 시간 차이는 관측된 차이이며 원인 증명은 아닙니다.', uncertainty: '누락 자료가 있는 사건은 평균에서 제외했습니다.'};
  ok(await planned.call(event({call_id: 'planned-specialist', batch_id: 'planned-specialist', plan_id: 'plan-one', step_id: 'maintenance', phase: 'completed', analysis: injection + '\n실제 전문 회신입니다.'})));
  const chartGroup = minutes => ({total_events: 2, confirmed_events: 1, mean_confirmed_minutes: minutes, mean_denominator: minutes == null ? 0 : 1, not_confirmed_events: 0, unassessable_events: 1});
  const chartResult = {ok: true, summary: {...chartGroup(12), total_events: 4, mean_denominator: 2}, comparisons: [{conditions: {equipment_id: 'EQ-02'}, groups: {planned_start: chartGroup(6), maintenance: chartGroup(18)}, maintenance_minus_planned_minutes: 12}, {conditions: {equipment_id: 'EQ-03'}, groups: {planned_start: chartGroup(null), maintenance: chartGroup(null)}, maintenance_minus_planned_minutes: null}], events: [
    {event_id: 'KEEP', equipment_id: 'EQ-02', restart_type: 'maintenance', state: 'confirmed', resumed_at: '2026-09-10T10:00:00', confirmed_after_minutes: 18, evidence_record_ids: ['EMS-KEEP']},
    {event_id: 'OTHER-TYPE', equipment_id: 'EQ-02', restart_type: 'planned_start', state: 'confirmed', confirmed_after_minutes: 6, evidence_record_ids: ['EMS-OTHER']},
    {event_id: 'OTHER-EQUIPMENT', equipment_id: 'EQ-03', restart_type: 'maintenance', state: 'unassessable', confirmed_after_minutes: null, evidence_record_ids: ['EMS-OTHER-EQ']},
  ], message: '합성 관측치이며 원인을 확정하지 않습니다.'};
  ok(await planned.call(event({kind: 'comparison', system: undefined, call_id: 'planned-compare', batch_id: 'planned-compare', plan_id: 'plan-one', step_id: 'compare', phase: 'completed', result: chartResult})));
  ok(await planned.call({...planEvent, seq: 2, phase: 'completed', steps: completedSteps, conclusion: '정비 후 재개 구간을 우선 확인하세요.', next_action: '같은 조건의 재개 절차를 점검하세요.', limitations: '합성 자료의 관측 차이이며 원인을 확정하지 않습니다.', changes: ['추가 비교 필요성을 반영했습니다.']}));
  assert.equal(planned.q('detail-title').textContent, '조건별 비교');
  assert.equal(planned.q('detail-rationale').hidden, false); assert.match(planned.q('detail-rationale').textContent, /관측된 차이/);
  assert.match(planned.q('detail-rationale').textContent, /같은 조건의 계획 기동/);
  assert.match(planned.q('detail-summary').textContent, /누락 자료가 있는 사건/);
  planned.q('detail-data-tab').click(); assert.equal(planned.q('detail-body').hidden, false);
  assert.ok(planned.q('detail-body').textContent.includes('확인 / 미확인 / 판정 불가'));
  planned.q('view-summary').click();
  assert.equal(planned.q('detail-section').hidden, true); assert.match(planned.q('summary-conclusion').textContent, /정비 후 재개 구간/);
  assert.match(planned.q('summary-next').textContent, /재개 절차/); assert.equal(planned.q('summary-limits').hidden, false);
  const bars = descendants(planned.q('summary-charts')).filter(node => node.className === 'chart-bar');
  assert.equal(bars.length, 4); assert.match(bars[0].textContent, /6분/); assert.match(bars[1].textContent, /18분/); assert.match(bars[2].textContent, /계산 불가/); assert.doesNotMatch(bars[2].textContent, /0분/);
  assert.equal(bars[1].children[1].children[0].style.width, '100%');
  bars[1].click(); assert.equal(planned.q('selected-evidence').hidden, false); assert.match(planned.q('selected-evidence').textContent, /EMS-KEEP/); assert.doesNotMatch(planned.q('selected-evidence').textContent, /OTHER/);
  assert.equal(planned.context.EES_INJECTION, undefined);
  assert.equal(ok(await planned.call({...planEvent, seq: 1, phase: 'running'})).updated, false);
  assert.match(planned.q('summary-conclusion').textContent, /정비 후 재개 구간/);
  planned.q('summary-findings').children[0].click(); assert.equal(planned.q('plan-screen').hidden, false); assert.equal(planned.q('detail-title').textContent, '정비 이력 확인'); assert.equal(planned.q('detail-body').hidden, true);
  console.log('PASS registered plan, actual step state, summary-first tabs, recorded reasons/judgment/limits, exact charts, filtered evidence and old-plan rejection');

  const woPython = `import asyncio, importlib.util, json, sys
from pathlib import Path
p = Path('agent-pack/skills/ems-work-order/scripts/wo_demo_tool.py')
spec = importlib.util.spec_from_file_location('actual_wo_panel', p)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m.WORK_PANEL_SCRIPT = Path('agent-pack/skills/cross-system-analysis/ui/work-panel.js').read_text(encoding='utf-8')
r = json.load(sys.stdin); captured = []
async def callback(event): captured.append(event['data']['code']); return {'ok': True}
asyncio.run(m._call(r['action'], callback, {'chat_id': 'chat-a'}, **r.get('values', {})))
print(json.dumps(captured[0]))
`;
  const runWO = async (action, values = {}) => {
    const captured = spawnSync(process.env.PYTHON || 'python', ['-c', woPython], {cwd: root, input: JSON.stringify({action, values}), encoding: 'utf8', timeout: 10000, env: {...process.env, PYTHONUTF8: '1'}});
    assert.equal(captured.status, 0, captured.stderr || String(captured.error || ''));
    return ok(await planned.run(JSON.parse(captured.stdout)));
  };
  let woState = await runWO('view');
  const actualWO = planned.document.getElementById('ees-wo-demo-panel'), woQ = id => actualWO.shadowRoot.getElementById(id), launcherBeforeSwitch = planned.launcher();
  assert.equal(planned.host(), null); assert.equal(actualWO.isConnected, true);
  woState = await runWO('update', {expected_revision: woState.revision, changes: {equipment_id: 'KR-CA-211', title: '정비 점검', description: '공통 패널의 작성 내용', type: '점검', priority: '일반'}});
  woQ('description').value = '사용자가 직접 작성한 요청'; woQ('description').fire('input');
  const actualDraft = JSON.parse(JSON.stringify(planned.window.__eesWODemoV1.view()));
  woQ('work-tab-analysis').click(); planned.flush();
  assert.equal(actualWO.isConnected, false); assert.ok(planned.host()); assert.equal(planned.launcher(), launcherBeforeSwitch);
  assert.equal(planned.q('work-analysis').focused, true);
  assert.equal(planned.q('work-equipment').disabled, false); assert.equal(planned.q('work-wo').disabled, false);
  planned.q('work-equipment').click(); planned.flush();
  assert.equal(planned.host(), null); assert.equal(actualWO.isConnected, true); assert.equal(planned.window.__eesWODemoV1.view().screen, 'equipment');
  assert.equal(woQ('work-tab-equipment').focused, true);
  woQ('work-tab-wo').click(); planned.flush();
  assert.equal(woQ('description').value, actualDraft.fields.description); assert.equal(planned.window.__eesWODemoV1.view().revision, actualDraft.revision);
  woQ('form').fire('submit'); const reviewedText = woQ('review-values').textContent;
  woQ('work-tab-analysis').click(); planned.q('work-wo').click(); planned.flush();
  assert.equal(woQ('review').hidden, false); assert.equal(woQ('review-values').textContent, reviewedText);
  woQ('close').click(); planned.flush(); assert.equal(planned.host(), null); assert.equal(actualWO.isConnected, false); assert.equal(planned.column.style.minWidth, '');
  assert.equal(planned.launcher().title, '업무 패널 열기');
  planned.route('/c/elsewhere'); planned.route('/c/chat-a'); planned.flush();
  assert.equal(planned.launcher(), launcherBeforeSwitch); assert.equal(actualWO.isConnected, false);
  planned.launcher().click(); planned.flush(); assert.equal(actualWO.isConnected, true); assert.equal(woQ('review-values').textContent, reviewedText);
  assert.equal(descendants(planned.body).filter(node => node.id === 'ees-work-panel-toggle').length, 1);
  assert.equal(planned.flush(), 0);
  console.log('PASS real analysis + real WO execute payloads, one launcher/three screens, manual draft/review retention and min-width/closed-route restoration');

  // End-to-end boundary: capture the real standalone compiled Python sender,
  // then execute its JS payload, including non-ASCII/code-like request content.
  const python = `import asyncio, json, sys, types
from pathlib import Path
sys.path.insert(0, str(Path('scripts').resolve()))
from ees_demo_assets import load_manifest
manifest = load_manifest(Path('.'))
item = next(t for t in manifest['tools'] if t['id'] == 'ees_specialists')
m = types.ModuleType('compiled_cooperation_capture'); sys.modules[m.__name__] = m
exec(compile(item['content'], '<registered-tool>', 'exec'), m.__dict__)
event = json.load(sys.stdin)
record = {'panel': {k: v for k, v in event.items() if k not in ('request','queries','analysis','analysis_truncated','error')}, 'request': event['request'], 'queries': event['queries'], 'analysis': event['analysis'], 'analysis_truncated': event['analysis_truncated']}
step = {'id': 'ems', 'type': 'specialist', 'status': 'pending', 'call_ids': []}
plan = {'snapshot': {'version': 1, 'kind': 'plan', 'chat_id': event['chat_id'], 'message_id': event['message_id'], 'call_id': 'plan1', 'batch_id': 'plan1', 'plan_id': 'plan1', 'seq': 0, 'phase': 'planned', 'title': '계획', 'steps': [step]}}
record['plan'] = plan; record['step'] = step; record['panel'].update(plan_id='plan1', step_id='ems')
captured = []
async def emitter(value): captured.append(value['data']['code'])
asyncio.run(m._panel(emitter, record, event['phase']))
print(json.dumps(captured[-1]))
`;
  const captured = spawnSync(process.env.PYTHON || 'python', ['-c', python], {cwd: root, input: JSON.stringify(event({request: {question: injection + ' 한글 질문', kind: 'initial'}})), encoding: 'utf8', timeout: 15000, env: {...process.env, PYTHONUTF8: '1'}});
  assert.equal(captured.status, 0, captured.stderr || String(captured.error || ''));
  const compiledEnv = environment(); ok(await compiledEnv.run(JSON.parse(captured.stdout))); assert.ok(compiledEnv.q('detail-body').textContent.includes(injection + ' 한글 질문')); assert.equal(compiledEnv.context.EES_INJECTION, undefined);
  console.log('PASS actual ApplyDemo compiled Python sender → execute payload → production panel');
})().catch(error => { console.error(error); process.exitCode = 1; });
