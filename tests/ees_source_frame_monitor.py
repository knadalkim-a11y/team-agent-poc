"""Pre-document, per-animation-frame visibility evidence for the real browser.

This observes the packaged page only. It never hides, moves, or replaces product
elements. Native conversation contents and the intentionally retained settings
dialog are allowed; the retired Native navigation chrome is not.
"""
import json


FRAME_MONITOR = r"""(() => {
  const evidence = window.__eesSourceFrameEvidence = {
    started: performance.now(), label: 'first-load', samples: [], sourceSeen: false
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
    evidence.samples.push({
      at: performance.now(), label: evidence.label, path: location.pathname,
      source, menu, bodyHidden, missingSource, legacy,
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
    for label in labels:
        selected = [item for item in samples if item['label'] == label]
        case.assertGreaterEqual(len(selected), 3, 'No meaningful frame coverage: ' + label)
        case.assertTrue(any(item['source'] and item['sourceText'] and item['menu']
                            for item in selected), 'Source regions were blank: ' + label)
        case.assertTrue(any(item['content'] or item['adminDialog'] for item in selected),
                        'No intended page content was visible: ' + label)
