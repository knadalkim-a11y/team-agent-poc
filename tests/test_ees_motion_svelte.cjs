/* Production Svelte lifecycle functions, executed without reimplementing their state guards. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const patch = fs.readFileSync(path.join(__dirname, '../frontend/patches/0001-ees-native-hooks.patch'), 'utf8');
function component(name) {
  if (process.env.EES_TEST_FRONTEND_SOURCE_DIR) {
    return fs.readFileSync(path.join(process.env.EES_TEST_FRONTEND_SOURCE_DIR,'src/lib/components/ees',name+'.svelte'),'utf8');
  }
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
// Exercise the production declarations, keyboard handler and pointer arithmetic.
// The packaged browser gate owns transitions, actual layout/hit-testing and focus.
function chatHarness(width = 1920, compact = false, selection = {}) {
  const shell=component('EesShell');
  const env={width,$eesCompact:compact,s:{...selection},smallSize:width<1200,smallOpen:false,
    overlay:false,expanded:false,transientWidth:null,chatOpen:false,chatState:'',dockAvailable:0,widthLimit:0,preferred:0,chatWidth:0,
    $showSettings:false,actions:[],tick:()=>Promise.resolve(),chatToggle:element(),chatSurface:element(),
    dragX:0,dragWidth:0,resizing:false,admin:false,document:{activeElement:null,querySelectorAll:()=>[]},
    getComputedStyle:()=>({visibility:'visible'})};
  env.chatSurface.querySelector=()=>null;
  env.chatSurface.querySelectorAll=()=>[];
  env.eesAction=value=>env.actions.push(value);
  const {stripTypeScriptTypes}=require('node:module');
  const f=between(shell,'async function setChatOpen(', '\n\tfunction clearPrivateDrafts(');
  const clamp=shell.split('\n').find(line=>line.includes('const clamp = '));
  const reactive=['dockAvailable','overlay','widthLimit','preferred','chatWidth','chatOpen','chatState'].map(name=>{
    const declaration=shell.split('\n').find(line=>line.includes('$: '+name+' = '));
    assert.ok(declaration,name);return declaration.replace('$: ','');
  }).join('\n');
  const funcs=Function('env',`with(env){${stripTypeScriptTypes(clamp+'\n'+f)};return {refresh(){${reactive}},setWidth,resizeStart,resizeMove,resizeEnd,resizeCancel,resizeKey,chatEscape,chatKeydown,setChatOpen,toggleChatExpanded};}`)(env);
  funcs.refresh(); return {env,...funcs};
}
function scopePositionHarness({ compact = true, width = 480, height = 768, bottom = 172 } = {}) {
  const documentListeners = new Map(), windowListeners = new Map(), closed = [];
  const inside = {}, style = {}, node = {
    style, closest: () => ({ getAttribute: () => String(compact) }),
    contains: target => target === inside,
    get offsetHeight() { return Math.min(360, parseFloat(style.maxHeight) || 360); }
  };
  const env = {
    trigger: { getBoundingClientRect: () => ({ left: 8, bottom }) },
    close: restore => closed.push(restore),
    document: { addEventListener: (name, fn) => documentListeners.set(name, fn), removeEventListener: name => documentListeners.delete(name) },
    window: { innerWidth: width, innerHeight: height,
      addEventListener: (name, fn) => windowListeners.set(name, fn), removeEventListener: name => windowListeners.delete(name) }
  };
  const source = between(component('EesScopeSelect'), 'function positionScope(', '\n\tfunction outside(')
    .replace('node: HTMLDivElement', 'node').replace('event: Event', 'event').replace('event.target as Node', 'event.target');
  const action = bind(source, env, 'positionScope')(node);
  return { node, inside, closed, documentListeners, windowListeners, action };
}
test('compact scope keeps readable width outside the rail and stays inside small viewports', () => {
  for (const size of [{ width: 1920 }, { width: 480 }, { width: 360, height: 250, bottom: 210 }, { width: 220 }]) {
    const width = size.width, height = size.height || 768, h = scopePositionHarness(size), s = h.node.style;
    assert.equal(s.position, 'fixed');
    assert.equal(parseFloat(s.width), Math.min(240, width - 16));
    assert.ok(parseFloat(s.left) >= 8);
    assert.ok(parseFloat(s.left) + parseFloat(s.width) <= width - 8);
    assert.ok(parseFloat(s.top) >= 8);
    assert.ok(parseFloat(s.top) + h.node.offsetHeight <= height - 8);
    h.action.destroy();
  }
  const expanded = scopePositionHarness({ compact: false });
  assert.equal(expanded.node.style.position, 'fixed');
  assert.equal(expanded.node.style.width, '240px'); expanded.action.destroy();
  assert.equal(expanded.documentListeners.size + expanded.windowListeners.size, 0);
});
test('compact scope allows list scroll but closes after anchor movement and removes listeners', () => {
  const h = scopePositionHarness();
  h.documentListeners.get('scroll')({ target: h.inside }); assert.deepEqual(h.closed, []);
  h.documentListeners.get('scroll')({ target: {} }); assert.deepEqual(h.closed, [false]);
  h.windowListeners.get('resize')(); assert.deepEqual(h.closed, [false, false]);
  h.action.destroy(); assert.equal(h.documentListeners.size + h.windowListeners.size, 0);
});
test('work takes the remainder after the actual rail and chat; 1116 is the first compact split',()=>{
  for(const [width,compact,work,chat] of [[1920,false,1104,560],[1536,false,720,560],[1366,true,830,480],[1280,true,744,480],[1117,true,640,421],[1116,true,640,420]]){
    const h=chatHarness(width,compact); if(width<1200){h.env.smallOpen=true;h.refresh();}
    assert.equal(h.env.chatState,'docked');assert.equal(h.env.chatWidth,chat,width);
    assert.equal(width-(compact?56:256)-chat,work);
  }
  for(const width of [1115,480]){const h=chatHarness(width,true);
    assert.equal(h.env.chatState,'closed');h.env.smallOpen=true;h.refresh();assert.equal(h.env.chatState,'overlay');}
  const h=chatHarness(1280,false);h.env.s.chat_open=true;h.refresh();
  assert.equal(h.env.chatState,'overlay','An expanded sidebar must count against the available space');
});
test('private chat width is distinct from old panel width; authoring does not force a fixed work center',()=>{
  const h=chatHarness(1920,false,{mode:'author',tab:'procedures',panel_width:420,panel_open:false});
  assert.equal(h.env.chatWidth,560);assert.equal(h.env.chatState,'docked');
  h.env.s.chat_width=690;h.refresh();assert.equal(h.env.chatWidth,690);
  h.env.s.chat_open=false;h.refresh();assert.equal(h.env.chatState,'closed');
});
test('dock drag uses the left edge of chat; Home, End and arrows preserve minimum work width',()=>{
  const h=chatHarness(1280,true);
  const handle={focus(){},setPointerCapture(id){assert.equal(id,1);}};
  h.resizeStart({button:0,currentTarget:handle,clientX:800,pointerId:1,preventDefault(){}});
  h.resizeMove({clientX:736});h.refresh();assert.equal(h.env.chatWidth,544);
  h.resizeEnd();assert.deepEqual(h.env.actions.pop(),{action:'chat_width',width:544});
  for(const [key,value] of [['Home',420],['End',584],['ArrowLeft',496],['ArrowRight',464]]){
    h.refresh();h.resizeKey({key,preventDefault(){}});assert.deepEqual(h.env.actions.pop(),{action:'chat_width',width:value});
  }
  h.env.expanded=true;h.refresh();h.setWidth(500,true);assert.deepEqual(h.env.actions,[]);
  const narrow=chatHarness(480,true);narrow.setWidth(510,true);assert.deepEqual(narrow.env.actions,[]);
});
test('narrow chat toggles locally; desktop display is an account preference and nested Escape stays local',async()=>{
  const narrow=chatHarness(480,true);await narrow.setChatOpen(true,false);narrow.refresh();
  assert.equal(narrow.env.chatState,'overlay');assert.deepEqual(narrow.env.actions,[]);
  const input={closest(selector){return selector==='[role="dialog"]'?narrow.env.chatSurface:null;}};
  const event=target=>({key:'Escape',target,defaultPrevented:false,stopPropagation(){this.stopped=true;},preventDefault(){this.defaultPrevented=true;}});
  assert.match(component('EesShell'),/on:keydown\|capture=\{chatEscape\}/);
  const nested=event({closest:()=>({})});narrow.chatEscape(nested);assert.equal(nested.stopped,undefined);
  const composing={...event(input),isComposing:true};narrow.chatEscape(composing);assert.equal(composing.stopped,undefined);
  const suggestion={getClientRects:()=>[{}],closest:()=>null};
  narrow.env.document.querySelectorAll=()=>[suggestion];
  const suggestionEscape=event(input);narrow.chatEscape(suggestionEscape);assert.equal(suggestionEscape.stopped,undefined);
  narrow.env.document.querySelectorAll=()=>[];
  const dismissed=event(input);narrow.chatEscape(dismissed);await flush();narrow.refresh();
  assert.equal(dismissed.stopped,true);assert.equal(narrow.env.chatState,'closed');assert.equal(narrow.env.chatToggle.focused,1);
  const wide=chatHarness(1920);await wide.setChatOpen(false,false);assert.deepEqual(wide.env.actions,[{action:'chat_open',open:'false'}]);
});
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
test('retained scope cancels closing synchronously without leaving it inert',async()=>{
  const scope=scopeHarness();scope.set(true);await flush();scope.set(false);scope.set(true);
  assert.equal(scope.m.pending.size,0);assert.equal(scope.env.dropdown.inert,false);
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

function navigationScopeProps(kind, { system, factories, systems = [{ id: 'EMS', allowed: true }, { id: 'APC', allowed: true }], actor = 'actor', path = '/c/chat', tab = 'overview' }) {
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
