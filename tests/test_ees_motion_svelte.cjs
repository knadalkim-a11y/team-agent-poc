/* Production Svelte lifecycle functions, executed without reimplementing their state guards. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const patch = fs.readFileSync(path.join(__dirname, '../frontend/patches/0001-ees-native-hooks.patch'), 'utf8');
function component(name) {
  const key = `diff --git a/src/lib/components/ees/${name}.svelte`;
  const start = patch.indexOf(key), end = patch.indexOf('diff --git ', start + key.length);
  return patch.slice(start, end < 0 ? undefined : end).split('\n').filter(line => line.startsWith('+') && !line.startsWith('+++')).map(line => line.slice(1)).join('\n');
}
function between(source, start, end) { const at = source.indexOf(start); assert.ok(at >= 0); return source.slice(at, source.indexOf(end, at)); }
function bind(source, env, name) { return Function('env', `with(env) { ${source} return ${name}; }`)(env); }
const flush = async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); };
function element() { return { inert: false, focused: 0, focus() { this.focused++; }, removeAttribute() {}, contains(node) { return node === this; } }; }
function motion() {
  const pending = new Map(), opened = [];
  const api = {
    open(node) { api.cancel(node); node.inert = true; opened.push(node); },
    close(node, callbacks = {}) { if (pending.has(node)) return pending.get(node).promise; let resolve; const promise = new Promise(yes => { resolve = yes; }); pending.set(node, { promise, resolve, callbacks }); node.inert = true; return promise; },
    cancel(node) { const item = pending.get(node); if (item) { pending.delete(node); item.resolve(false); } },
    finish(node, { restoreFocus = true } = {}) { const item = pending.get(node); if (!item) return; pending.delete(node); item.callbacks.cleanup?.(); if (restoreFocus) item.callbacks.restoreFocus?.(); item.resolve(true); }
  };
  return { api, pending, opened };
}
function scopeHarness(kind = 'factory') {
  const m = motion(), env = { window: { __eesMotionV1: m.api }, tick: () => Promise.resolve(), scopeVersion: 0, pendingSelection: null, selectionExitBoundary: null, previousBoundary: 'initial', selectionContext: 'route-and-permissions', value: 'old', kind, document: { activeElement: null, body: element(), documentElement: element() }, shown: false, open: false, opened: '', restoreOnClose: true, query: 'kept while closing', dropdown: element(), trigger: element() };
  const source = between(component('EesScopeSelect'), 'function syncScope(', '\n\tonDestroy(').replace('wantsOpen: boolean, activeKind: string', 'wantsOpen, activeKind');
  const sync = bind(source, env, 'syncScope');
  env.syncScope = sync;
  const reactiveCall = component('EesScopeSelect').match(/\$:\s*(syncScope\([^;]+\));/)[1];
  const react = Function('env', `with(env) { ${reactiveCall}; }`);
  env.retireScope = bind(between(component('EesScopeSelect'), 'function retireScope()', '\n\t$: syncScope'), env, 'retireScope');
  env.close = bind(between(component('EesScopeSelect'), 'function close(', '\n\tfunction allowedOptions'), env, 'close');
  const boundary = bind(between(component('EesScopeSelect'), 'function syncBoundary(', '\n\tfunction retireScope').replace('next: string, context: string, selected: string, exit: string', 'next, context, selected, exit'), env, 'syncBoundary');
  const choose = bind(between(component('EesScopeSelect'), 'function choose(', '\n\tfunction keydown'), env, 'choose');
  env.eesAction = action => { env.value = action.factoryId ?? action.systemId; };
  return { env, m, choose, react() { react(env); }, boundary(next, context = env.selectionContext, selected = env.value, exit = next) { boundary(next, context, selected, exit); }, set(open, opened = open ? kind : '') { env.open = open; env.opened = opened; sync(open, opened); } };
}
function panelHarness() {
  const m = motion(), trigger = element(), env = { window: { __eesMotionV1: m.api }, tick: () => Promise.resolve(), previousPanelOpen: null, previousPanelOverlay: null, panelOpen: false, panelOverlay: true, panelClosing: false, panelClose: Promise.resolve(true), nativeRoute: false, mounted: true, admin: false, panelRegion: element(), panel: element(), document: { getElementById: () => trigger, body: element(), documentElement: element() }, $showSettings: false, actions: [] };
  env.eesAction = action => env.actions.push(action);
  const shell = component('EesShell');
  const sync = bind(between(shell, 'function syncPanelMotion(', '\n\t$: if (mounted)').replace('open: boolean, overlay: boolean, native: boolean', 'open, overlay, native'), env, 'syncPanelMotion');
  const focusSource = between(shell, 'focusPanel: async', '\n\t\treferenceHost:').replace('(open: boolean)', '(open)');
  const focus = Function('env', `with(env) { return { ${focusSource} }.focusPanel; }`)(env);
  const key = bind(between(shell, 'function panelKeydown(', '\n\tfunction clearPrivateDrafts').replace('event: KeyboardEvent', 'event').replaceAll('(event.target as Element)', 'event.target'), env, 'panelKeydown');
  return { env, m, trigger, focus, key, set(open, overlay = true, native = false) { env.panelOpen = open; env.panelOverlay = overlay; env.nativeRoute = native; sync(open, overlay, native); } };
}
test('scope close before its opening tick never opens a stale menu and restores focus after completion', async () => {
  const h = scopeHarness(); h.set(true); h.set(false); await flush();
  assert.equal(h.m.opened.length, 0); assert.equal(h.env.shown, true); assert.equal(h.env.trigger.focused, 0);
  h.m.api.finish(h.env.dropdown); assert.equal(h.env.shown, false); assert.equal(h.env.query, ''); assert.equal(h.env.trigger.focused, 1);
});
test('scope reopening cancels pending cleanup and overrides any stale inert snapshot', async () => {
  const h = scopeHarness(); h.set(true); await flush(); h.set(false); h.set(true); await flush();
  assert.equal(h.env.shown, true); assert.equal(h.env.dropdown.inert, false); assert.equal(h.env.trigger.focused, 0); assert.equal(h.m.pending.size, 0);
});
test('opening a sibling retires closing scope content immediately without restoring old focus', async () => {
  const h = scopeHarness(); h.set(true); await flush(); h.set(false); h.set(false, 'system');
  assert.equal(h.env.shown, false); assert.equal(h.m.pending.size, 0); assert.equal(h.env.trigger.focused, 0);
});
test('attached panel changes layout immediately and only fades content on open', async () => {
  const h = panelHarness(); h.set(true, false); await flush(); assert.deepEqual(h.m.opened, [h.env.panel]);
  h.set(false, false); assert.equal(h.env.panelClosing, false); assert.equal(h.m.pending.size, 0); await h.focus(false); assert.equal(h.trigger.focused, 1);
});
test('overlay animates only the panel and returns focus after its completion', async () => {
  const h = panelHarness(); h.set(true); await flush();
  assert.deepEqual(h.m.opened, [h.env.panelRegion], 'Conversation has no panel backdrop animation');
  h.set(false); const focus = h.focus(false); await flush();
  assert.equal(h.env.panelClosing, true); assert.equal(h.trigger.focused, 0);
  assert.equal(h.m.pending.size, 1, 'Panel completion must be the only exit gate');
  h.m.api.finish(h.env.panelRegion); await focus;
  assert.equal(h.env.panelClosing, false); assert.equal(h.trigger.focused, 1);
});
test('overlay reopening cancels old cleanup and focus without leaving interaction inert', async () => {
  const h = panelHarness(); h.set(true); await flush(); h.set(false); const focus = h.focus(false); h.set(true); await flush(); await focus;
  assert.equal(h.env.panelClosing, false); assert.equal(h.env.panelRegion.inert, false); assert.equal(h.trigger.focused, 0); assert.equal(h.m.pending.size, 0);
});
test('a responsive overlay-to-attached change cancels exit instead of reserving space until timeout', async () => {
  const h = panelHarness(); h.set(true); await flush(); h.set(false); h.set(false, false);
  assert.equal(h.env.panelClosing, false); assert.equal(h.m.pending.size, 0);
});
test('overlay Escape preserves nested consumed keys and ignores attached/native/settings surfaces', () => {
  const h = panelHarness(), event = () => ({ key: 'Escape', target: h.env.panelRegion, defaultPrevented: false, stopPropagation() { this.stopped = true; }, preventDefault() { this.defaultPrevented = true; } });
  h.set(true); h.key({ ...event(), defaultPrevented: true }); assert.equal(h.env.actions.length, 0);
  h.set(true, false); h.key(event()); assert.equal(h.env.actions.length, 0);
  h.set(true, true); h.env.$showSettings = true; h.key(event()); assert.equal(h.env.actions.length, 0);
  h.env.$showSettings = false; h.key(event()); assert.deepEqual(h.env.actions, [{ action: 'close_panel' }]);
});

test('overlay close completion does not steal a new focus chosen on the released conversation', async () => {
  const h = panelHarness(); h.set(true); await flush(); h.env.document.activeElement = h.env.panelRegion;
  h.set(false); const focus = h.focus(false); await flush(); h.env.document.activeElement = element();
  h.m.api.finish(h.env.panelRegion); await focus;
  assert.equal(h.trigger.focused, 0);
});

test('queued panel entry does not restart after its shell is destroyed', async () => {
  const h = panelHarness(); h.set(true); h.env.mounted = false; h.env.panelRegion = undefined; h.env.panel = undefined;
  await flush(); assert.equal(h.m.opened.length, 0);
});

test('retained scope and overlay stop closing synchronously before reactive inert bindings update', async () => {
  const scope = scopeHarness(); scope.set(true); await flush(); scope.set(false); scope.set(true);
  assert.equal(scope.m.pending.size, 0); assert.equal(scope.env.dropdown.inert, false);
  const panel = panelHarness(); panel.set(true); await flush(); panel.set(false); panel.set(true);
  assert.equal(panel.m.pending.size, 0); assert.equal(panel.env.panelRegion.inert, false);
});
test('own scope selection updates business value immediately and keeps the common exit until completion', async () => {
  for (const boundaryFirst of [true, false]) {
    const h = scopeHarness(); h.set(true); await flush(); h.choose({ id: 'new' });
    assert.equal(h.env.value, 'new'); assert.equal(h.env.opened, ''); assert.equal(h.env.trigger.focused, 0);
    h.env.open = false;
    if (boundaryFirst) h.boundary('selected-new');
    h.set(false);
    if (!boundaryFirst) h.boundary('selected-new');
    assert.equal(h.env.shown, true); assert.equal(h.env.dropdown.inert, true);
    assert.equal(h.m.pending.size, 1); assert.equal(h.env.trigger.focused, 0);
    h.m.api.finish(h.env.dropdown);
    assert.equal(h.env.shown, false); assert.equal(h.env.trigger.focused, 1);
  }
});
test('scope selection cannot exempt a different option or a changed permission/navigation context', async () => {
  for (const [context, selected] of [['changed-route-or-permissions', 'new'], ['route-and-permissions', 'another']]) {
    const h = scopeHarness(); h.set(true); await flush(); h.choose({ id: 'new' }); h.set(false);
    h.boundary('invalidated', context, selected);
    assert.equal(h.env.shown, false); assert.equal(h.m.pending.size, 0); assert.equal(h.env.trigger.focused, 0);
  }
});
test('own selection exemption is consumed once and does not cover later navigation', async () => {
  const h = scopeHarness(); h.set(true); await flush(); h.choose({ id: 'new' }); h.set(false);
  h.boundary('selected-new'); assert.equal(h.env.shown, true);
  h.boundary('another-workflow');
  assert.equal(h.env.shown, false); assert.equal(h.m.pending.size, 0); assert.equal(h.env.trigger.focused, 0);
});
test('choosing the already selected option does not exempt a later navigation boundary', async () => {
  const h = scopeHarness(); h.set(true); await flush(); h.choose({ id: h.env.value }); h.set(false);
  assert.equal(h.m.pending.size, 1); assert.equal(h.env.pendingSelection, null);
  h.boundary('another-workflow');
  assert.equal(h.env.shown, false); assert.equal(h.m.pending.size, 0); assert.equal(h.env.trigger.focused, 0);
});
test('overlay Escape owns shell bubbling before Native unconditional document CLOSE_MODAL handling', () => {
  const shell = component('EesShell');
  assert.match(shell, /class="ees-source-shell"\s+on:keydown=\{panelKeydown\}/);
  assert.doesNotMatch(shell, /<svelte:window[^>]*on:keydown/);
  const h = panelHarness(); h.set(true); let nativeCalls = 0;
  const event = { key: 'Escape', defaultPrevented: false, stopped: false,
    target: h.env.panelRegion, preventDefault() { this.defaultPrevented = true; }, stopPropagation() { this.stopped = true; } };
  h.key(event); if (!event.stopped) { nativeCalls++; event.preventDefault(); }
  assert.equal(nativeCalls, 0); assert.deepEqual(h.env.actions, [{ action: 'close_panel' }]);
  const scopeEvent = { ...event, stopped: false, defaultPrevented: false, target: { closest() { return {}; } } };
  h.key(scopeEvent); assert.equal(scopeEvent.stopped, false); assert.equal(h.env.actions.length, 1);
});

test('overlay Escape outside the panel leaves Native bubbling and panel state untouched', () => {
  for (const location of ['composer', 'sidebar']) {
    const h = panelHarness(); h.set(true); let nativeCalls = 0;
    const event = { key: 'Escape', target: { ...element(), location }, defaultPrevented: false, stopped: false, prevented: 0,
      preventDefault() { this.prevented++; this.defaultPrevented = true; }, stopPropagation() { this.stopped = true; } };
    h.key(event);
    assert.deepEqual(h.env.actions, [], location);
    assert.equal(event.prevented, 0, location); assert.equal(event.stopped, false, location);
    if (!event.stopped) { nativeCalls++; event.preventDefault(); }
    assert.equal(nativeCalls, 1, 'Native document CLOSE_MODAL still handles the outside Escape once');
    assert.equal(h.env.panelOpen, true);
  }
});

test('panel close never restores the opener when focus started outside the panel', async () => {
  for (const overlay of [true, false]) {
    const h = panelHarness(); h.set(true, overlay); await flush();
    const composer = element(); h.env.document.activeElement = composer;
    h.set(false, overlay); const focus = h.focus(false); await flush();
    h.m.api.finish(h.env.panelRegion); await focus;
    assert.equal(h.trigger.focused, 0, `outside focus with overlay=${overlay}`);
    assert.equal(h.env.document.activeElement, composer);
  }
});

test('panel close restores the opener when panel focus falls back to body during closing', async () => {
  for (const overlay of [true, false]) {
    const h = panelHarness(); h.set(true, overlay); await flush();
    h.env.document.activeElement = h.env.panelRegion;
    h.set(false, overlay); const focus = h.focus(false); h.env.document.activeElement = h.env.document.body;
    await flush(); h.m.api.finish(h.env.panelRegion); await focus;
    assert.equal(h.trigger.focused, 1, `panel-owned focus with overlay=${overlay}`);
  }
});

test('Native dialog and menu targets keep their own Escape handling', () => {
  const h = panelHarness(); h.set(true);
  for (const surface of ['dialog', '[role="dialog"]', '[role="menu"]']) {
    const event = { key: 'Escape', defaultPrevented: false, target: { closest(selector) { return selector.includes(surface) ? {} : null; } },
      preventDefault() { throw Error('Native surface key was captured'); }, stopPropagation() { throw Error('Native surface key was captured'); } };
    h.key(event);
  }
  assert.equal(h.env.actions.length, 0);
});

test('external boundary retirement cannot reopen from a stale derived open value in the same flush', async () => {
  const h = scopeHarness(); h.set(true); await flush();
  h.boundary('new-server-permissions');
  assert.equal(h.env.opened, ''); assert.equal(h.env.open, true, 'Simulate derived value from before boundary close');
  assert.equal(h.env.shown, false);
  h.react(); await flush();
  const source = component('EesScopeSelect');
  for (const [attribute, expected] of [['aria-expanded', false], ['aria-controls', undefined], ['inert', true], ['aria-hidden', true]]) {
    const expression = source.match(new RegExp(`${attribute}=\\{([^}]+)\\}`))[1];
    const actual = Function('env', `with(env) { return (${expression}); }`)(h.env);
    assert.equal(actual, expected, `${attribute} follows the same live opened state`);
  }
  assert.equal(h.env.shown, false); assert.equal(h.m.pending.size, 0);
  assert.equal(h.m.opened.length, 1, 'No new opening animation after external invalidation');
  assert.equal(h.env.trigger.focused, 0);
});

function navigationScopeProps(kind, { system, factories, systems = [{ id: 'EMS', allowed: true }, { id: 'APC', allowed: true }], actor = 'actor', path = '/c/chat', tab = 'my_work' }) {
  const source = component('EesNavigation');
  const env = { $page: { url: { pathname: path, search: '' } }, cap: { actor_id: actor }, $eesSnapshot: { native_id: '' },
    s: { mode: 'work', tab, system_id: system, factory_id: '', chat_id: 'chat' }, $eesCompact: false, author: false, systems, factories };
  const evaluate = expression => Function('env', `with(env) { return (${expression}); }`)(env);
  for (const name of ['scopeLocation', 'scopeBoundary', 'scopeSystemExitBoundary', 'scopeSelectionContext']) {
    const statement = source.split('\n').find(line => line.includes(`$: ${name} = `));
    env[name] = evaluate(statement.slice(statement.indexOf(' = ') + 3, -1));
  }
  const markup = source.split('\n').find(line => line.includes(`options={${kind === 'factory' ? 'factories' : 'systems'}}`));
  const prop = name => evaluate(markup.match(new RegExp(`${name}=\\{([^}]+)\\}`))[1]);
  return { boundary: env.scopeBoundary, context: prop('selectionContext'), exit: prop('exitBoundary') };
}
for (const cached of [true, false]) test(`own system selection keeps exit and focus across ${cached ? 'cached' : 'responding'} factory catalog replacement`, async () => {
  const emsFactories = [{ id: '', name: 'All factories' }, { id: 'factory-1', system_id: 'EMS', allowed: true }];
  const apcFactories = [{ id: '', name: 'All factories' }];
    const h = scopeHarness('system');
    const origin = navigationScopeProps('system', { system: 'EMS', factories: emsFactories });
    h.env.selectionContext = origin.context; h.env.previousBoundary = origin.boundary; h.env.value = 'EMS';
    h.set(true); await flush(); h.choose({ id: 'APC' }); h.set(false);
    const first = navigationScopeProps('system', { system: 'APC', factories: cached ? apcFactories : emsFactories });
    h.boundary(first.boundary, first.context, 'APC', first.exit);
    assert.equal(h.env.shown, true); assert.equal(h.m.pending.size, 1);
    const response = navigationScopeProps('system', { system: 'APC', factories: apcFactories });
    h.boundary(response.boundary, response.context, 'APC', response.exit);
    assert.equal(h.env.shown, true); assert.equal(h.m.pending.size, 1); assert.equal(h.env.trigger.focused, 0);
    h.m.api.finish(h.env.dropdown);
    assert.equal(h.env.shown, false); assert.equal(h.env.trigger.focused, 1);
});
test('system exit exception never covers system permission, account, route, destination or opened-catalog invalidation', async () => {
  const factories = [{ id: 'factory-1', system_id: 'EMS', name: 'Factory 1' }];
  const origin = navigationScopeProps('system', { system: 'EMS', factories });
  const selected = navigationScopeProps('system', { system: 'APC', factories });
  for (const change of [{ systems: [{ id: 'APC', allowed: false }] }, { actor: 'another-actor' }, { path: '/workspace/skills' }, { tab: 'records' }, { system: 'EMS' }]) {
    const h = scopeHarness('system'); h.env.selectionContext = origin.context; h.env.previousBoundary = origin.boundary; h.env.value = 'EMS';
    h.set(true); await flush(); h.choose({ id: 'APC' }); h.set(false);
    h.boundary(selected.boundary, selected.context, 'APC', selected.exit);
    const next = navigationScopeProps('system', { system: 'APC', factories, ...change });
    h.boundary(next.boundary, next.context, change.system || 'APC', next.exit);
    assert.equal(h.env.shown, false); assert.equal(h.m.pending.size, 0); assert.equal(h.env.trigger.focused, 0);
  }
  for (const kind of ['system', 'factory']) {
    const h = scopeHarness(kind), initial = navigationScopeProps(kind, { system: 'EMS', factories });
    h.env.previousBoundary = initial.boundary; h.set(true); await flush();
    const renamed = navigationScopeProps(kind, { system: 'EMS', factories: [{ ...factories[0], name: 'Renamed factory' }] });
    h.boundary(renamed.boundary, renamed.context, h.env.value, renamed.exit); h.react();
    assert.equal(h.env.shown, false); assert.equal(h.env.opened, ''); assert.equal(h.env.trigger.focused, 0);
  }
});
