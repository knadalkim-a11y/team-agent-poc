"""Pre-document, per-animation-frame visibility evidence for the real browser.

This observes the packaged page only. It never hides, moves, or replaces product
elements. Native conversation contents and the intentionally retained settings
dialog are allowed; the retired Native navigation chrome is not.
"""
import json


FRAME_MONITOR = r"""(() => {
  const evidence = window.__eesSourceFrameEvidence = {
    started: performance.now(), label: 'first-load', samples: [], sourceSeen: false,
    loadingGuard: false, scopeExpectation: null, scopeRequests: [],
    nativeReturn: null, nativeReturns: []
  };
  const visible = element => {
    if (!element || !element.getClientRects().length) return false;
    const rect = element.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0 || rect.bottom <= 0 || rect.right <= 0 ||
        rect.top >= innerHeight || rect.left >= innerWidth) return false;
    for (let node = element; node instanceof Element; node = node.parentElement) {
      const style = getComputedStyle(node);
      if (style.display === 'none' || style.visibility !== 'visible' || Number(style.opacity) === 0)
        return false;
    }
    return true;
  };
  // Observe the actual translated loading copy, including the legacy work
  // panel. A source shell can stay visible while its entire contents flash.
  const loading = selector => [...document.querySelectorAll(selector + ' *')]
    .filter(node => visible(node) &&
      /^(불러오는 중[….]*|업무 정보를 불러오는 중입니다[.]?|Loading[….]*|Loading work information[….]*)$/i
        .test(node.textContent.trim()) &&
      ![...node.children].some(child => visible(child) && child.textContent.trim() === node.textContent.trim()))
    .map(node => node.textContent.trim());
  // Observe successful body delivery independently of the product snapshot.
  // A first-scope assertion must also fail against a version with no loading
  // flag. Observe the real consumer body: a cloned stream can finish parsing
  // after the product has already rendered the delivered result.
  const originalFetch = window.fetch;
  window.fetch = function(input, options) {
    const url = new URL(typeof input === 'string' ? input : input.url, location.href);
    const endpoint = url.pathname.match(/^\/api\/ees-work\/(workspace|operations)$/)?.[1];
    const expected = evidence.scopeExpectation;
    const matches = expected && endpoint &&
      (url.searchParams.get('system_id') || '') === expected.system &&
      (endpoint !== 'workspace' || (url.searchParams.get('factory_id') || '') === expected.factory);
    const row = matches ? {label: expected.label, endpoint, system: expected.system,
      factory: expected.factory, started: performance.now(), received: null} : null;
    if (row) {
      expected.started = true;
      evidence.scopeRequests.push(row);
    }
    return originalFetch.call(this, input, options).then(response => {
      if (row && response.ok) {
        const originalJSON = response.json.bind(response);
        response.json = (...args) => originalJSON(...args).then(body => {
          if (body.ok === true) {
            row.received = performance.now();
            expected.received[endpoint] = true;
          }
          return body;
        });
      }
      return response;
    });
  };
  const scopeEmpty = () => {
    const copy = /^(등록된 업무 절차가 없습니다[.]?|지금 처리할 내 업무가 없습니다[.]?|저장된 진행 건이 없습니다[.]?|조회할 이전 기록이 없습니다[.]?|No procedures are registered[.]?)$/;
    const nodes = [...document.querySelectorAll('#ees-work-entry *, #ees-work-panel *')];
    const empty = nodes.filter(node => visible(node) &&
      (copy.test(node.textContent.trim()) || /^아직 (업무 절차|워크플로우)가 없습니다[.]?/.test(node.textContent.trim()) ||
       /의 업무 절차\s*0개$/.test(node.textContent.trim())) &&
      ![...node.children].some(child => visible(child) && child.textContent.trim() === node.textContent.trim()))
      .map(node => node.textContent.trim());
    for (const node of document.querySelectorAll('#ees-work-entry [data-action=procedures] small'))
      if (visible(node) && node.textContent.trim() === '0') empty.push('업무 절차 배지 0');
    for (const node of document.querySelectorAll('#ees-work-designer .ew-author-heading small'))
      if (visible(node) && node.textContent.trim() === '0개') empty.push('워크플로우 목록 0개');
    return empty;
  };
  const navigationCurrent = () => [...document.querySelectorAll('#ees-work-entry [aria-current]')]
    .filter(node => visible(node) && !['', 'false'].includes(node.getAttribute('aria-current')))
    .map(node => ({key: node.dataset.action === 'native_open'
      ? 'native_open:' + node.dataset.nativeId : node.dataset.action,
      ariaCurrent: node.getAttribute('aria-current'), text: node.textContent.trim()}));
  const rightPanels = () => {
    const panels = [];
    for (const header of document.querySelectorAll('#ees-work-designer > header')) {
      if (!visible(header)) continue;
      const title = header.firstChild?.textContent.trim();
      if (title === '도구' || title === '도구 · 공용') panels.push('tools');
      if (title === '업무 절차' || title === '워크플로우') panels.push('procedures');
    }
    for (const header of document.querySelectorAll('#ees-work-panel .ew-work-heading h2'))
      if (visible(header) && header.textContent.trim() === '공장·접근 범위') panels.push('workspace_admin');
    for (const header of document.querySelectorAll('#ees-work-panel .ew-panel-header strong'))
      if (visible(header) && header.textContent.trim() === '내 업무') panels.push('my_work');
    return panels;
  };
  // Arm before physical CDP input, but start the boundary at the real click.
  // This observer does not dispatch clicks or modify any product DOM/state.
  document.addEventListener('click', event => {
    const expected = evidence.nativeReturn;
    if (!expected || expected.clickedAt !== null || !event.target.closest?.(expected.selector)) return;
    expected.clickedAt = performance.now();
    expected.trusted = event.isTrusted;
    expected.beforeCurrent = navigationCurrent();
  }, true);
  const observe = () => {
    const shell = document.querySelector('[data-ees-source-shell]');
    const sidebar = document.querySelector('[data-ees-source-sidebar]');
    const chat = document.querySelector('#chat-container');
    const workspace = document.querySelector('#workspace-container');
    const dialog = document.querySelector('[role=dialog][aria-modal=true]:has(#settings-tabs-container)');
    const legacy = [];
    for (const node of document.querySelectorAll('#sidebar, .sidebar-new-chat-icon, #sidebar-search-button')) {
      if (!node.closest('[data-ees-source-sidebar]') && visible(node))
        legacy.push(node.id || node.className);
    }
    // The old workspace tabs were hidden after mount. Source workspace heading
    // and Native settings tabs are intentional; original workspace link tabs
    // outside the source sidebar are not.
    for (const node of document.querySelectorAll('a[href^="/workspace/"]')) {
      if (!node.closest('[data-ees-source-sidebar], #workspace-container, [role=dialog]') && visible(node))
        legacy.push('workspace-tab:' + node.getAttribute('href'));
    }
    const source = visible(shell), menu = visible(sidebar);
    if (visible(chat) && !source) legacy.push('native-chat-without-source-shell');
    const bodyHidden = !!document.body && getComputedStyle(document.body).visibility !== 'visible';
    const missingSource = evidence.sourceSeen && !source;
    evidence.sourceSeen ||= source;
    const expected = evidence.scopeExpectation;
    const scopePending = !!expected?.unknown && !!expected.started &&
      !expected.endpoints.every(endpoint => expected.received[endpoint]);
    const menuCurrent = navigationCurrent(), panels = rightPanels();
    const menuMode = [...document.querySelectorAll('#ees-work-entry [data-action=mode][aria-pressed=true]')]
      .filter(visible).map(node => node.dataset.mode);
    const menuLoading = loading('#ees-work-entry'), panelLoading = loading('#ees-work-panel');
    const targetLoading = [...document.querySelectorAll('#ees-work-panel #ees-work-content [data-ees-target-loading]')]
      .filter(visible).map(node => node.textContent.trim());
    const returning = evidence.nativeReturn && evidence.nativeReturn.clickedAt !== null
      ? evidence.nativeReturn : null;
    const returnSelectionBad = returning && (menuCurrent.length !== 1 ||
      menuCurrent.some(item => !returning.allowed.includes(item.key)));
    // Only the newly requested different-destination boundary allows a local
    // target placeholder. A missing/full-loading menu or any older panel is
    // still a failure; other tests keep their original no-loading contract.
    const destinationLoading = !!returning && menuCurrent.length === 1 &&
      menuCurrent[0].key === returning.destination && menuMode.length === 1 &&
      menuMode[0] === (returning.destination === 'my_work' ? 'work' : 'author') &&
      !panels.includes(returning.previous) && targetLoading.length > 0 &&
      targetLoading.length === panelLoading.length &&
      panelLoading.every((text, index) => text === targetLoading[index]);
    evidence.samples.push({
      at: performance.now(), label: evidence.label, path: location.pathname,
      source, menu, bodyHidden, missingSource, legacy,
      menuCurrent, rightPanels: panels,
      menuMode, targetLoading,
      nativeReturnLabel: returning?.label || null,
      nativeReturnUnexpectedSelection: !!returnSelectionBad,
      nativeReturnPreviousPanel: returning ? panels.filter(kind => kind === returning.previous) : [],
      nativeReturnDestinationLoading: destinationLoading,
      loadingGuard: evidence.loadingGuard,
      menuLoading, panelLoading,
      scopeLabel: expected?.label || null, scopePending,
      scopeEmptyBeforeResponse: scopePending ? scopeEmpty() : [],
      scopeLocalLoading: [...document.querySelectorAll('[data-ees-scope-loading]')]
        .filter(visible).map(node => ({region: node.dataset.eesScopeLoading, text: node.textContent.trim()})),
      scopeControls: visible(document.querySelector('#ees-work-system-trigger')) &&
        [...document.querySelectorAll('#ees-work-entry [data-action=mode]')].filter(visible).length === 2 &&
        !![...document.querySelectorAll('#ees-work-entry [data-action=my_work], #ees-work-entry [data-action=procedures]')].find(visible),
      content: visible(chat) || visible(workspace), adminDialog: visible(dialog),
      sourceText: source && !!shell.textContent.trim(),
      startupGate: document.documentElement?.dataset.eesStartup || null
    });
    evidence.frame = requestAnimationFrame(observe);
  };
  evidence.frame = requestAnimationFrame(observe);
})();
"""


def install(case):
    identifier = case.browser.call('Page.addScriptToEvaluateOnNewDocument', {
        'source': FRAME_MONITOR})['identifier']
    case.addCleanup(lambda: case.browser.call('Page.removeScriptToEvaluateOnNewDocument', {
        'identifier': identifier}))
    return identifier


def mark(case, label):
    case.browser.evaluate('window.__eesSourceFrameEvidence.label=' + json.dumps(label))


def guard_loading(case):
    """Arm only after initial data and the tested panel targets are loaded."""
    case.browser.evaluate('window.__eesSourceFrameEvidence.loadingGuard=true')


def begin_scope_read(case, label, *, system, factory='', unknown=True):
    """Arm a first/known scope boundary before physical selection."""
    expected = {'label': label, 'system': system, 'factory': factory, 'unknown': unknown,
                'started': False, 'endpoints': ['workspace', 'operations'], 'received': {}}
    case.browser.evaluate('window.__eesSourceFrameEvidence.label=' + json.dumps(label) +
                          ';window.__eesSourceFrameEvidence.scopeExpectation=' + json.dumps(expected))


def begin_native_return(case, label, *, selector, native, destination, previous):
    """Observe a different-menu return from the actual physical click onward."""
    # C45 removed the Native tools menu; its B10-2 route has no selected Native item.
    before = [] if native == 'tools' else ['native_open:' + native]
    expected = {'label': label, 'selector': selector, 'native': native,
                'destination': destination, 'previous': previous, 'expectedBefore': before,
                'allowed': before + [destination],
                'clickedAt': None, 'trusted': False, 'beforeCurrent': []}
    case.browser.evaluate('(()=>{const e=window.__eesSourceFrameEvidence;'
                          'e.label=' + json.dumps(label) + ';e.nativeReturn=' + json.dumps(expected) +
                          ';e.nativeReturns.push(e.nativeReturn);})()')


def end_native_return(case):
    case.browser.evaluate('window.__eesSourceFrameEvidence.nativeReturn=null')


def collect(case, *, labels=(), minimum_frames=3):
    # Wait on observed frames, not a sleep or a product DOM mutation.
    for label in labels:
        case.wait('window.__eesSourceFrameEvidence.samples.filter(s=>s.label===' +
                  json.dumps(label) + ').length >= ' + str(minimum_frames))
    return case.browser.evaluate('JSON.parse(JSON.stringify(window.__eesSourceFrameEvidence))')


def assert_clean(case, evidence, *, labels=()):
    samples = evidence['samples']
    case.assertGreater(len(samples), 2, 'The frame monitor must actually observe the page')
    case.assertTrue(evidence['sourceSeen'], 'The source shell never rendered')
    failures = [item for item in samples if item['legacy'] or item['missingSource']
                or item['bodyHidden'] or item['startupGate']]
    case.assertEqual(failures, [], 'Observed retired Native chrome or a page-wide hiding gate')
    loading = [item for item in samples if item.get('loadingGuard')
               and (item.get('menuLoading') or
                    (item.get('panelLoading') and not item.get('nativeReturnDestinationLoading')))]
    case.assertEqual(loading[:10], [],
                     'Observed EES loading placeholders after initial data: ' + str(len(loading)) + ' frames')
    premature_empty = [item for item in samples if item.get('scopeEmptyBeforeResponse')]
    case.assertEqual(premature_empty[:10], [],
                     'Observed none/zero before first scope response: ' + str(len(premature_empty)) + ' frames')
    wrong_selection = [item for item in samples if item.get('nativeReturnUnexpectedSelection')]
    case.assertEqual(wrong_selection[:10], [],
                     'Observed selection outside the Native item/destination: ' + str(len(wrong_selection)) + ' frames')
    previous_panel = [item for item in samples if item.get('nativeReturnPreviousPanel')]
    case.assertEqual(previous_panel[:10], [],
                     'Observed the previous right-hand panel during Native return: ' + str(len(previous_panel)) + ' frames')
    for expected in evidence.get('nativeReturns', []):
        case.assertTrue(expected['trusted'], 'Native return did not start with physical input: ' + expected['label'])
        case.assertEqual([item['key'] for item in expected['beforeCurrent']], expected['expectedBefore'])
        frames = [item for item in samples if item.get('nativeReturnLabel') == expected['label']]
        case.assertGreaterEqual(len(frames), 3, 'Missing Native return frame coverage: ' + expected['label'])
        case.assertTrue(any(expected['destination'] in item['rightPanels'] and
                            [entry['key'] for entry in item['menuCurrent']] == [expected['destination']]
                            for item in frames), 'Destination selection/content never rendered: ' + expected['label'])
    for label in labels:
        selected = [item for item in samples if item['label'] == label]
        case.assertGreaterEqual(len(selected), 3, 'No meaningful frame coverage: ' + label)
        case.assertTrue(any(item['source'] and item['sourceText'] and item['menu']
                            for item in selected), 'Source regions were blank: ' + label)
        case.assertTrue(any(item['content'] or item['adminDialog'] for item in selected),
                        'No intended page content was visible: ' + label)
