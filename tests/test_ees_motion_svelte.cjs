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
function scopeHarness() {
  const m = motion(), env = { window: { __eesMotionV1: m.api }, tick: () => Promise.resolve(), scopeVersion: 0, selectionFocus: null, document: { activeElement: null, body: element(), documentElement: element() }, shown: false, open: false, opened: '', restoreOnClose: true, query: 'kept while closing', dropdown: element(), trigger: element() };
  const source = between(component('EesScopeSelect'), 'function syncScope(', '\n\tonDestroy(').replace('wantsOpen: boolean, activeKind: string', 'wantsOpen, activeKind');
  const sync = bind(source, env, 'syncScope');
  const retire = bind(between(component('EesScopeSelect'), 'function retireScope()', '\n\t$: syncScope'), env, 'retireScope');
  return { env, m, retire, set(open, opened = open ? 'factory' : '') { env.open = open; env.opened = opened; sync(open, opened); } };
}
function panelHarness() {
  const m = motion(), trigger = element(), env = { window: { __eesMotionV1: m.api }, tick: () => Promise.resolve(), previousPanelOpen: null, previousPanelOverlay: null, panelOpen: false, panelOverlay: true, panelClosing: false, panelClose: Promise.resolve(true), nativeRoute: false, mounted: true, admin: false, panelRegion: element(), panelBackdrop: element(), panel: element(), document: { getElementById: () => trigger }, $showSettings: false, actions: [] };
  env.eesAction = action => env.actions.push(action);
  const shell = component('EesShell');
  const sync = bind(between(shell, 'function syncPanelMotion(', '\n\t$: if (mounted)').replace('open: boolean, overlay: boolean, native: boolean', 'open, overlay, native'), env, 'syncPanelMotion');
  const focusSource = between(shell, 'focusPanel: async', '\n\t\treferenceHost:').replace('(open: boolean)', '(open)');
  const focus = Function('env', `with(env) { return { ${focusSource} }.focusPanel; }`)(env);
  const key = bind(between(shell, 'function panelKeydown(', '\n\tfunction clearPrivateDrafts').replace('event: KeyboardEvent', 'event').replace('(event.target as Element)', 'event.target'), env, 'panelKeydown');
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
test('overlay panel and backdrop finish together before focus return', async () => {
  const h = panelHarness(); h.set(true); await flush(); h.set(false); const focus = h.focus(false); await flush();
  assert.equal(h.env.panelClosing, true); assert.equal(h.trigger.focused, 0); h.m.api.finish(h.env.panelRegion); await flush(); assert.equal(h.trigger.focused, 0);
  h.m.api.finish(h.env.panelBackdrop); await focus; assert.equal(h.env.panelClosing, false); assert.equal(h.trigger.focused, 1);
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
  const h = panelHarness(), event = () => ({ key: 'Escape', defaultPrevented: false, stopPropagation() { this.stopped = true; }, preventDefault() { this.defaultPrevented = true; } });
  h.set(true); h.key({ ...event(), defaultPrevented: true }); assert.equal(h.env.actions.length, 0);
  h.set(true, false); h.key(event()); assert.equal(h.env.actions.length, 0);
  h.set(true, true); h.env.$showSettings = true; h.key(event()); assert.equal(h.env.actions.length, 0);
  h.env.$showSettings = false; h.key(event()); assert.deepEqual(h.env.actions, [{ action: 'close_panel' }]);
});

test('overlay close completion does not steal a new focus chosen on the released conversation', async () => {
  const h = panelHarness(); h.set(true); await flush(); h.env.document.activeElement = h.env.panelRegion;
  h.set(false); const focus = h.focus(false); await flush(); h.env.document.activeElement = element();
  h.m.api.finish(h.env.panelRegion); h.m.api.finish(h.env.panelBackdrop); await focus;
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
test('scope selection boundary retires stale choices immediately and preserves its explicit focus return', async () => {
  const h = scopeHarness(); h.set(true); await flush(); const option = element();
  h.env.document.activeElement = option; h.env.selectionFocus = option; h.set(false); h.retire();
  assert.equal(h.env.shown, false); assert.equal(h.m.pending.size, 0); assert.equal(h.env.trigger.focused, 1);
});
test('scope permission or navigation boundary never requests selection focus or steals a newer focus', async () => {
  for (const selection of [false, true]) {
    const h = scopeHarness(); h.set(true); await flush(); h.env.selectionFocus = selection ? element() : null;
    h.env.document.activeElement = element(); h.set(false); h.retire();
    assert.equal(h.env.shown, false); assert.equal(h.env.trigger.focused, 0);
  }
});
test('overlay Escape owns shell bubbling before Native unconditional document CLOSE_MODAL handling', () => {
  const shell = component('EesShell');
  assert.match(shell, /class="ees-source-shell"\s+on:keydown=\{panelKeydown\}/);
  assert.doesNotMatch(shell, /<svelte:window[^>]*on:keydown/);
  const h = panelHarness(); h.set(true); let nativeCalls = 0;
  const event = { key: 'Escape', defaultPrevented: false, stopped: false,
    target: { closest() { return null; } }, preventDefault() { this.defaultPrevented = true; }, stopPropagation() { this.stopped = true; } };
  h.key(event); if (!event.stopped) { nativeCalls++; event.preventDefault(); }
  assert.equal(nativeCalls, 0); assert.deepEqual(h.env.actions, [{ action: 'close_panel' }]);
  const scopeEvent = { ...event, stopped: false, defaultPrevented: false, target: { closest() { return {}; } } };
  h.key(scopeEvent); assert.equal(scopeEvent.stopped, false); assert.equal(h.env.actions.length, 1);
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
