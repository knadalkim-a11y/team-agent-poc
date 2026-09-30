// Production view transitions with independent DOM scroll surfaces and geometry.
// This is a lifecycle regression fixture, not a Native browser/visual acceptance test.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../branding/ees/ui/ees-work-view.js'), 'utf8');

function fixture() {
  const elements = new Map(), observers = [], preferences = {sidebarWidth: '480', sidebar: 'true'};
  function element(id = '') {
    const el = {id, dataset: {}, isConnected: false, scrollTop: 0, scrollLeft: 0, children: [], innerHTML: '',
      style: {setProperty(key, value) {this[key] = value;}, removeProperty(key) {delete this[key];}},
      classList: {add() {}, remove() {}, toggle() {}},
      setAttribute(key, value) {this[key] = value;}, querySelector: () => null, querySelectorAll: () => [],
      contains(target) {return this === target || this.children.includes(target);},
      remove() {this.isConnected = false;this.scrollTop = 0;this.scrollLeft = 0;},
      append(child) {child.isConnected = true;this.children.push(child);elements.set(child.id, child);},
      insertBefore(child) {this.append(child);}, after(child) {column.append(child);},
      replaceChildren() {this.children = [];}, getBoundingClientRect() {return {width: this.width || 0, height: 0};}
    };
    if (id)elements.set(id, el);
    return el;
  }
  const row = element('row');row.width = 1664;
  const column = element('column');column.parentElement = row;column.width = 360;
  const anchor = element('chat-pane');anchor.parentElement = column;
  const search = element('sidebar-search-button'), entry = element('ees-work-entry');entry.isConnected = search.isConnected = true;
  const content = element('ees-work-content'), tabs = element('ees-work-tabs'), host = element('ees-work-panel'), divider = element('ees-work-resizer');
  let detailMain = null, detailWrapper = null, table = null, html = '';
  Object.defineProperty(content, 'innerHTML', {get: () => html, set(value) {
    html = value;detailMain = value.includes('class="ew-v4-detail-main"') ? element() : null;
    detailWrapper = detailMain ? element() : null;
    table = value.includes('class="ew-v4-table-scroll"') ? element() : null;
    content.children = [];host.children = [content, detailMain, detailWrapper, table].filter(Boolean);
  }});
  content.querySelector = selector => ({'.ew-v4-detail-main': detailMain, '.ew-v4-detail': detailWrapper, '.ew-v4-table-scroll': table})[selector] || null;
  host.querySelector = selector => ({'#ees-work-content': content, '#ees-work-tabs': tabs, '.ew-v4-table-scroll': table})[selector] || null;
  host.remove = () => {host.isConnected = false;for (const el of host.children)el.remove();};
  const document = {body: {dataset: {}}, activeElement: null,
    querySelector(selector) {if (selector === '#chat-container #chat-pane')return anchor;const el = elements.get(selector.slice(1));return el?.isConnected ? el : null;},
    createElement: () => element(), getElementById: id => elements.get(id)?.isConnected ? elements.get(id) : null};
  const window = {innerWidth: 1920, getComputedStyle: () => ({overflowY: window.innerWidth <= 760 ? 'visible' : 'auto'}),
    ResizeObserver: class {constructor(callback) {this.callback = callback;this.connected = false;observers.push(this);} observe(target) {this.target = target;this.connected = true;} disconnect() {this.connected = false;}}};
  const context = {document, window, localStorage: {getItem: key => preferences[key], setItem() {throw new Error('layout must not rewrite saved preferences');}}};
  const marker = 'return Object.freeze({render,prepare,sync,';
  const exposed = source.replace(marker, `return Object.freeze({_layout:{
    setup:value=>{host=value.host;divider=value.divider;},sidebar,renderContext,
    preferred:()=>preferredWidth
  },render,prepare,sync,`);
  vm.createContext(context);vm.runInContext(exposed, context);
  const site = {id: 'a', name: '공장'};
  const definition = {version: 1, sites: {a: site}, tools: {}, nodes: {
    p: {id: 'p', type: 'p', name: '절차', children: ['t']},
    t: {id: 't', parent: 'p', type: 't', name: '단계', children: ['j', 'j2']},
    j: {id: 'j', parent: 't', type: 'j', name: '작업', mode: 'manual'},
    j2: {id: 'j2', parent: 't', type: 'j', name: '다른 작업', mode: 'manual'}
  }};
  const current = {id: 'case', version: 1, revision: 1, site, system: 'EMS', process_id: 'p', status: 'in_progress', definition, jobs: {}, node_states: {}};
  let snapshot = {state: {case: current, catalog: definition, cases: []}, selectedCaseId: 'case', selectedId: 't', processId: 'p', browsingSite: 'a', browsingSystem: 'EMS', category: 'setup', runView: 'current', chatRoute: true};
  const view = vm.runInContext('createWorkView({callbacks:{registerPanel(){}}})', context);
  view._layout.setup({host, divider});
  const render = patch => {snapshot = {...snapshot, ...patch};view.renderPanel(snapshot);};
  const scroll = (surface, top, left = 0) => {surface.scrollTop = top;surface.scrollLeft = left;view.handleEvent({type: 'scroll', target: surface});};
  const key = key => view.handleEvent({type: 'keydown', key, target: {closest: selector => selector === '#ees-work-resizer' ? divider : null}});
  return {view, document, window, row, column, host, divider, content, current, preferences, observers, render, scroll, key,
    main: () => detailMain, detail: () => detailWrapper, table: () => table, exists: id => Boolean(document.querySelector('#' + id))};
}

test('initial sidebar, open, close, detached refresh and route exit keep separate shell and panel lifecycles', () => {
  const f = fixture();f.view._layout.sidebar();f.render();f.view._layout.renderContext();
  assert.equal(f.document.body.dataset.eesV4, '');assert.equal(f.document.body.dataset.eesWorkOpen, undefined);
  assert.equal(f.exists('ees-work-context'), false);assert.equal(f.exists('ees-v4-suggestions'), false);
  f.view.panelRegistration().open();
  assert.equal(f.document.body.dataset.eesWorkOpen, 'true');assert.ok(f.exists('ees-work-context'));assert.ok(f.exists('ees-v4-suggestions'));
  f.view.closeHost();f.render();f.view._layout.renderContext();
  assert.equal(f.document.body.dataset.eesV4, '');assert.equal(f.document.body.dataset.eesWorkOpen, undefined);
  assert.equal(f.exists('ees-work-context'), false);assert.equal(f.exists('ees-v4-suggestions'), false);
  assert.ok(f.observers.every(observer => !observer.connected));
  f.view.panelRegistration().open();f.render({chatRoute: false});f.view._layout.renderContext();
  assert.equal(f.exists('ees-work-context'), false);assert.equal(f.exists('ees-v4-suggestions'), false);
  f.render({chatRoute: true});f.view.panelRegistration().open();f.view.detach();
  assert.equal(f.exists('ees-work-context'), false);assert.equal(f.exists('ees-v4-suggestions'), false);
  assert.equal(f.document.body.dataset.eesV4, '', 'detaching work must not undo the sidebar style');
  f.view.reset();assert.equal(f.document.body.dataset.eesV4, undefined);
});

test('real detail, whole-detail small screen and list horizontal/vertical scroll survive target refresh and return', () => {
  const f = fixture();f.render();f.view.panelRegistration().open();
  f.scroll(f.content, 440);f.scroll(f.table(), 0, 72);
  f.render({selectedId: 'j'});assert.equal(f.main().scrollTop, 0);
  f.scroll(f.main(), 240);f.current.revision++;f.render();
  assert.equal(f.main().scrollTop, 240, 'rerender must restore the scrolling detail, not the hidden outer content');
  f.render({selectedId: 'j2'});assert.equal(f.main().scrollTop, 0);
  f.render({selectedId: 'j'});assert.equal(f.main().scrollTop, 240);
  f.view.closeHost();f.render();f.view.panelRegistration().open();assert.equal(f.main().scrollTop, 240);
  f.window.innerWidth = 700;f.view.updateLayout();assert.equal(f.detail().scrollTop, 240);
  f.scroll(f.detail(), 280);f.window.innerWidth = 1920;f.view.updateLayout();assert.equal(f.main().scrollTop, 280);
  f.render({selectedId: 't'});assert.equal(f.content.scrollTop, 440);assert.equal(f.table().scrollLeft, 72);
  f.render({selectedId: 'j', selectedCaseId: 'other', state: {case: {...f.current, id: 'other'}, catalog: f.current.definition, cases: []}});
  assert.equal(f.main().scrollTop, 0, 'a different case must not inherit an earlier target scroll');
});

test('actual available row width enables overlay without overwriting sidebar or Assistant preferences', () => {
  const f = fixture();f.render();f.view.panelRegistration().open();f.key('End');
  assert.equal(f.view._layout.preferred(), 600);assert.equal(f.column.style['--ees-v4-assistant-width'], '600px');
  assert.equal(f.document.body.dataset.eesAssistantOverlay, 'false');
  f.row.width = 1440;f.observers.at(-1).callback();
  assert.equal(f.host.dataset.compact, 'true', 'wide viewport with saved large columns still needs compact central inputs');
  assert.equal(f.document.body.dataset.eesAssistantOverlay, 'false');
  f.row.width = 800;f.window.innerWidth = 1280;f.observers.at(-1).callback();
  assert.equal(f.document.body.dataset.eesAssistantOverlay, 'true');assert.equal(f.divider.hidden, true);
  assert.equal(f.view._layout.preferred(), 600);
  f.row.width = 260;f.window.innerWidth = 700;f.view.updateLayout();
  assert.equal(f.column.style['--ees-v4-assistant-width'], '260px');assert.equal(f.view._layout.preferred(), 600);
  f.row.width = 1664;f.window.innerWidth = 1920;f.view.updateLayout();
  assert.equal(f.column.style['--ees-v4-assistant-width'], '600px');assert.equal(f.document.body.dataset.eesAssistantOverlay, 'false');
  assert.equal(f.divider.hidden, false);assert.deepEqual(f.preferences, {sidebarWidth: '480', sidebar: 'true'});
  f.view.closeHost();f.view.panelRegistration().open();assert.equal(f.view._layout.preferred(), 600);
});

test('default 1920 and 1366 widths preserve the three-column layout and Assistant closed state', () => {
  const f = fixture();f.render();f.view.panelRegistration().open();
  assert.equal(f.column.style['--ees-v4-assistant-width'], '360px');
  f.window.innerWidth = 1366;f.row.width = 1110;f.view.updateLayout();
  assert.equal(f.column.style['--ees-v4-assistant-width'], '320px');assert.equal(f.document.body.dataset.eesAssistantOverlay, 'false');
  const target = {dataset: {action: 'assistant_toggle'}, closest: selector => ['[data-action]', '[data-ees-work]'].includes(selector) ? target : null};
  f.view.handleEvent({type: 'click', target});assert.equal(f.document.body.dataset.eesAssistantOpen, 'false');
  f.row.width = 800;f.view.updateLayout();assert.equal(f.document.body.dataset.eesAssistantOpen, 'false');
  f.view.closeHost();f.view.panelRegistration().open();assert.equal(f.document.body.dataset.eesAssistantOpen, 'false');
});
