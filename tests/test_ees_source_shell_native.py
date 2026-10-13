"""Actual packaged source-shell navigation, observed before each paint frame.

The browser and frontend are real; login, stored conversations, model transport,
and Native capabilities are explicit synthetic fixtures. The workflow service
and its temporary SQLite state use the production implementation.
"""
import importlib
import json
import os
from pathlib import Path
from unittest.mock import patch

import ees_source_frame_monitor as frame_monitor
from ees_work_integrated_fixture import IntegratedNativeCase


class SourceShellNativeTests(IntegratedNativeCase):
    def enable_native_menus(self):
        # Native Tools also checks its ordinary feature flag. The explicit
        # capability fixture alone does not bypass that compiled route guard.
        self.server.native_plugins_enabled = True
        native = importlib.import_module(self.backend.__package__ + '.ees_workflow_native')

        async def access(_actor):
            return {'native_access': dict.fromkeys(
                ('models', 'knowledge', 'prompts', 'skills', 'tools', 'admin'), True),
                'native_access_available': True}

        provider = patch.object(native, 'native_workspace_access', access)
        provider.start()
        self.addCleanup(provider.stop)
        self.refresh()

    def capture_failure(self):
        super().capture_failure()
        if (not getattr(self, 'failure_evidence_captured', False)
                or getattr(self, 'frame_failure_captured', False)
                or not self.browser.session):
            return
        self.frame_failure_captured = True
        evidence = self.browser.evaluate('window.__eesSourceFrameEvidence || null')
        directory = Path(os.environ['EES_TEST_SCREENSHOT_DIR']) if os.environ.get('EES_TEST_SCREENSHOT_DIR') else Path(__file__).resolve().parents[1] / 'dist/ees-work-screenshots'
        directory.mkdir(parents=True, exist_ok=True)
        (directory / (self._testMethodName + '-failure-frames.json')).write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def step(self, label, selector, condition):
        frame_monitor.mark(self, label)
        self.click(selector)
        self.wait(condition)
        frame_monitor.collect(self, labels=(label,))

    def test_every_navigation_has_source_chrome_without_native_overlay_frames(self):
        self.enable_native_menus()
        workflow_id = self.author(name='화면 이동 검증 절차', jobs=2)
        run = self.start(workflow_id)
        frame_monitor.install(self)
        self.navigate('/c/existing-chat')
        self.wait("window.__eesNativeWorkV1 && document.querySelector('[data-ees-source-sidebar]') && document.querySelector('#chat-input.ProseMirror')")
        self.open_sidebar()
        frame_monitor.collect(self, labels=('first-load',))
        labels = ['first-load']

        frame_monitor.mark(self, 'work-open')
        self.open_run(workflow_id, run)
        frame_monitor.collect(self, labels=('work-open',))
        labels.append('work-open')
        self.step('right-overview', '#ees-work-panel [data-action=overview]',
                  "document.querySelector('#ees-work-panel [data-action=job]')")
        labels.append('right-overview')
        self.step('right-other-task', '#ees-work-panel [data-action=job][data-job-id=job-1]',
                  "document.querySelector('#ees-work-panel h2')?.textContent === '합성 작업 1'")
        labels.append('right-other-task')

        self.step('chat-list', '[data-action=chats]',
                  "[...document.querySelectorAll('a[href=\"/c/other-chat\"]')].some(e=>e.getBoundingClientRect().height > 0)")
        labels.append('chat-list')
        self.step('chat-list-open', 'a[href="/c/other-chat"]',
                  "location.pathname === '/c/other-chat' && document.querySelector('#chat-input.ProseMirror')")
        labels.append('chat-list-open')
        self.step('new-chat', '[data-action=new_chat]',
                  "location.pathname === '/' && window.__eesNativeDraftV1?.ready()")
        labels.append('new-chat')
        self.step('chat-list-again', '[data-action=chats]',
                  "[...document.querySelectorAll('a[href=\"/c/existing-chat\"]')].some(e=>e.getBoundingClientRect().height > 0)")
        labels.append('chat-list-again')
        self.step('chat-existing-return', 'a[href="/c/existing-chat"]',
                  "location.pathname === '/c/existing-chat' && document.querySelector('#chat-input.ProseMirror') && document.querySelector('#chat-container')?.textContent.includes('기존 대화 기록')")
        labels.append('chat-existing-return')

        self.step('work-authoring', '[data-action=mode][data-mode=author]',
                  "document.querySelector('#ees-work-designer')")
        labels.append('work-authoring')
        self.step('work-tools', '#ees-work-entry [data-action=tools]',
                  "document.querySelector('[data-author-action=tool_create]')")
        labels.append('work-tools')
        self.step('work-access', '#ees-work-entry [data-action=workspace_admin]',
                  "document.querySelector('#ees-work-panel h2')?.textContent === '공장·접근 범위'")
        labels.append('work-access')
        self.step('work-procedures', '#ees-work-entry [data-action=procedures]',
                  "document.querySelector('#ees-work-designer')")
        labels.append('work-procedures')
        for target in ('models', 'knowledge', 'prompts', 'skills', 'tools'):
            label = 'native-' + target
            self.step(label, '[data-action=native_open][data-native-id=' + target + ']',
                      'location.pathname === ' + json.dumps('/workspace/' + target)
                      + ' && document.querySelector("#workspace-container input")')
            labels.append(label)
        self.step('native-return', '#ees-work-entry [data-action=procedures]',
                  "location.pathname === '/c/existing-chat' && document.querySelector('#ees-work-designer')")
        labels.append('native-return')
        self.step('admin-open', '[data-action=native_open][data-native-id=admin]',
                  "document.querySelector('#settings-tabs-container [role=tab][aria-controls=tab-admin-general][aria-selected=true]')")
        labels.append('admin-open')
        self.step('admin-return', '#settings-tabs-container > button',
                  "!document.querySelector('#settings-tabs-container') && document.querySelector('#ees-work-designer')")
        labels.append('admin-return')

        evidence = frame_monitor.collect(self, labels=labels)
        directory = self.screenshot('source-shell-all-navigation-final')
        evidence['scope'] = 'Real packaged source frontend and physical CDP clicks; every animation frame, synthetic Native session/data, real temporary workflow service. Retained Native settings dialog is intentional.'
        evidence['counts'] = {label: sum(item['label'] == label for item in evidence['samples'])
                              for label in labels}
        evidence['native_bad_visible'] = sum(bool(item['legacy']) for item in evidence['samples'])
        (directory / 'source-shell-all-navigation-frames.json').write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        frame_monitor.assert_clean(self, evidence, labels=labels)
        self.assertEqual(self.server.completions, [], 'Navigation must not submit a conversation')

        # Negative control proves that the same observer catches even one frame
        # of retired Native chrome. It runs only after the product evidence was
        # frozen and is never counted as a product navigation or UI success.
        frame_monitor.mark(self, 'monitor-negative-control')
        self.browser.evaluate("""new Promise(resolve=>{
          const node=document.createElement('div');node.className='sidebar-new-chat-icon';
          node.style.cssText='position:fixed;top:0;left:0;width:80px;height:80px;background:red;z-index:999999';
          document.body.append(node);
          requestAnimationFrame(()=>requestAnimationFrame(()=>{node.remove();resolve(true);}));
        })""")
        negative = self.browser.evaluate("window.__eesSourceFrameEvidence.samples.filter(s=>s.label==='monitor-negative-control')")
        self.assertTrue(any(item['legacy'] for item in negative), 'Frame detector missed its visible negative control')
        (directory / 'source-shell-monitor-negative-control.json').write_text(
            json.dumps(negative, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
