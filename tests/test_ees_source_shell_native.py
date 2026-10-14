"""Actual packaged source-shell navigation, observed before each paint frame.

The browser and frontend are real; login, stored conversations, model transport,
and Native capabilities are explicit synthetic fixtures. The workflow service
and its temporary SQLite state use the production implementation.
"""
import importlib
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import time
from unittest.mock import patch
from urllib.parse import urlparse

import ees_source_frame_monitor as frame_monitor
from ees_work_integrated_fixture import IntegratedNativeCase
from native_ui_fixture import NativeUIHandler


class SourceShellNativeTests(IntegratedNativeCase):
    def scope_catalog_fixture(self, *, denied=False):
        """Real saved factories and grants; never replace workspace responses.

        Native login/chat storage remain synthetic, as in the shared fixture.
        Scope visibility and roles come from the production service and its
        actual HTTP response for the current limited account.
        """
        for index in range(1, 9):
            self.command('save_factory', factory_id='scope-factory-' + str(index),
                         system_id='EMS', name='합성 공장 ' + str(index).zfill(2),
                         attributes={'scope_private_attribute': 'not-in-selector-metadata'})
        if not denied:
            self.refresh()
            return
        self.scope_admin = self.server.user
        limited = deepcopy(self.scope_admin)
        limited.update(id='scope-user', name='권한 범위 검증 사용자',
                       email='scope-user@example.invalid', role='user')
        self.users[limited['id']] = limited
        for index in range(1, 8):
            self.command('save_access', principal_kind='user', principal_id=limited['id'],
                         system_id='EMS', factory_id='scope-factory-' + str(index),
                         roles=['manager' if index == 1 else 'participant'])
        self.scope_apc_grant = self.command('save_access', principal_kind='user',
            principal_id=limited['id'], system_id='APC', factory_id='*', roles=['manager'])
        self.server.user = limited
        for chat in self.server.chats.values():
            chat['user_id'] = limited['id']
        # Reload the Native session as the limited actor before entering a
        # draft. Updating only an in-memory service user would leave the
        # frontend authenticated as its previous administrator.
        self.navigate('/c/existing-chat')
        self.wait("document.querySelector('#chat-input.ProseMirror') && document.querySelector('#ees-work-system-trigger') && window.__eesNativeDraftV1?.ready()")
        self.open_sidebar()
        self.assertIsNotNone(self.refresh())
        response = self.scope_http_state()
        self.assertFalse(response['capabilities']['is_admin'])
        self.assertTrue(response['capabilities']['can_author'])
        self.assertEqual(response['capabilities']['managed_systems'], ['APC'])
        self.assertEqual(set(response['systems']), {'EMS', 'APC'})
        allowed = {item['id'] for item in response['factories']}
        self.assertEqual(allowed, {'scope-factory-' + str(index) for index in range(1, 8)})
        options = response['scope_options']
        systems = {item['id']: item for item in options['systems']}
        factories = {item['id']: item for item in options['factories']}
        self.assertEqual(len(factories), 8, 'Search threshold includes visible denied metadata')
        self.assertEqual({key for key, item in systems.items() if item['allowed']}, {'EMS', 'APC'})
        self.assertEqual((systems['EMS']['role'], systems['APC']['role']), ('participant', 'owner'))
        self.assertFalse(systems['FDC']['allowed'])
        self.assertEqual((factories['scope-factory-1']['role'], factories['scope-factory-2']['role']), ('owner', 'participant'))
        self.assertFalse(factories['scope-factory-8']['allowed'])
        self.assertEqual(factories['scope-factory-8']['role'], '')
        for item in options['systems']:
            self.assertEqual(set(item), {'id', 'name', 'role', 'allowed'})
        for item in options['factories']:
            self.assertEqual(set(item), {'id', 'name', 'system_id', 'role', 'allowed'})
        self.assertNotIn('not-in-selector-metadata', json.dumps(options))
        self.scope_api_evidence = {'source': 'Actual HTTP workspace response from production WorkflowService; real saved factory and access grants, synthetic Native session/chat storage only.',
            'actor_id': limited['id'], 'is_admin': response['capabilities']['is_admin'],
            'allowed_systems': response['systems'], 'allowed_factory_ids': sorted(allowed),
            'scope_options': options}

    def scope_http_state(self):
        response = self.browser.evaluate("fetch('/api/ees-work/workspace?system_id=EMS',{headers:{Authorization:'Bearer '+localStorage.getItem('token')}}).then(r=>r.json())")
        self.assertTrue(response.get('ok'), response)
        return response

    def scope_open(self, kind):
        trigger = '#ees-work-' + ('site' if kind == 'factory' else 'system') + '-trigger'
        self.click(trigger)
        self.wait('document.querySelector("[data-scope-dropdown=' + kind + ']")')
        self.assertEqual(self.read(trigger, 'ariaExpanded'), 'true')
        self.assertEqual(self.read(trigger, 'ariaHasPopup'), 'listbox')
        self.assertEqual(self.browser.evaluate('document.querySelectorAll("[data-scope-dropdown]").length'), 1)
        self.assertFalse(self.browser.evaluate('!!document.querySelector("#ees-work-dialog[open],dialog[open],[aria-modal=true]")'))
        geometry = self.browser.evaluate('''(()=>{const field=document.querySelector(''' + json.dumps(trigger) + '''),
          popup=document.querySelector('[data-scope-dropdown]'),list=popup.querySelector('[role=listbox]'),
          f=field.getBoundingClientRect(),p=popup.getBoundingClientRect(),l=list.getBoundingClientRect();
          return {field:{left:f.left,right:f.right,bottom:f.bottom},popup:{left:p.left,top:p.top,width:p.width,height:p.height},
            list:{height:l.height,scrollHeight:list.scrollHeight,clientHeight:list.clientHeight,
              overflow:getComputedStyle(list).overflowY},border:getComputedStyle(field).borderColor};})()''')
        self.assertGreaterEqual(geometry['popup']['top'], geometry['field']['bottom'] - 1)
        self.assertLessEqual(geometry['popup']['top'] - geometry['field']['bottom'], 12)
        self.assertAlmostEqual(geometry['popup']['left'], geometry['field']['left'], delta=1)
        self.assertLessEqual(geometry['list']['height'], 360.5)
        self.assertLessEqual(geometry['popup']['height'], 360.5)
        self.assertGreater(geometry['popup']['width'], 100)
        # Open-state blue must be visible on the field itself.
        colors = [int(value) for value in re.findall(r'\d+', geometry['border'])[:3]]
        self.assertEqual(len(colors), 3, geometry)
        self.assertGreater(colors[2], colors[0], geometry)
        return trigger, geometry

    def scope_closed(self, trigger, *, focus=True):
        self.wait('!document.querySelector("[data-scope-dropdown]")')
        self.assertEqual(self.read(trigger, 'ariaExpanded'), 'false')
        if focus:
            self.assertTrue(self.browser.evaluate('document.activeElement === document.querySelector(' + json.dumps(trigger) + ')'))

    def scope_activate_key(self, key):
        # CDP keyDown without text emits no keypress. Native buttons activate
        # Enter through that default event, so send the full physical key as
        # browser automation keyboards do; do not dispatch DOM click events.
        code, virtual, text = ('Enter', 13, '\r') if key == 'Enter' else ('Space', 32, ' ')
        self.browser.call('Input.dispatchKeyEvent', {'type': 'keyDown', 'key': key,
                          'code': code, 'windowsVirtualKeyCode': virtual,
                          'nativeVirtualKeyCode': virtual, 'text': text, 'unmodifiedText': text})
        self.browser.call('Input.dispatchKeyEvent', {'type': 'keyUp', 'key': key,
                          'code': code, 'windowsVirtualKeyCode': virtual,
                          'nativeVirtualKeyCode': virtual})

    def scope_search(self, text):
        # The general form helper ends with Tab; scope menus correctly close
        # on Tab. Keep focus in this search field while observing its results.
        self.click('#ees-factory-search')
        self.key('a', 65, 2)
        if text:
            self.browser.call('Input.insertText', {'text': text})
        else:
            self.key('Backspace', 8)

    def test_scope_three_dropdowns_anchor_keyboard_search_denied_and_focus(self):
        self.scope_catalog_fixture(denied=True)
        self.browser.evaluate("""(()=>{window.__scopeKeyboardEvidence=[];
          for(const type of ['keydown','keypress','keyup','click'])document.addEventListener(type,event=>{
            const node=event.target?.closest?.('[data-scope-trigger],[role=option],#ees-factory-search');
            if(node)window.__scopeKeyboardEvidence.push({type,key:event.key||'',code:event.code||'',
              trusted:event.isTrusted,target:node.id||node.dataset.factoryId||node.dataset.systemId||'',
              opened:!!document.querySelector('[data-scope-dropdown]')});
          },true);})()""")
        self.fill('#chat-input', '범위를 골라도 유지할 개인 대화 초안')
        draft = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        evidence = {}
        # Each of the three A2 states gets open, Esc/focus, Enter/Space open,
        # outside click and selection through real browser input events.
        for variant, kind, target, expected in (
                ('work-factory', 'factory', 'scope-factory-1', '합성 공장 01'),
                ('work-system', 'system', 'APC', 'APC'),
                ('workspace-system', 'system', 'EMS', 'EMS')):
            if variant == 'workspace-system':
                self.click('[data-action=mode][data-mode=author]')
                self.wait("document.querySelector('#ees-work-designer')")
                self.assertFalse(self.browser.evaluate("!!document.querySelector('#ees-work-site-trigger')"))
                self.assertIn('관리 시스템', self.text('#ees-work-entry'))
            trigger, geometry = self.scope_open(kind)
            evidence[variant] = geometry
            self.screenshot('source-scope-' + variant)
            self.key('Escape', 27)
            self.scope_closed(trigger)
            self.scope_activate_key('Enter')
            self.wait('document.querySelector("[data-scope-dropdown=' + kind + ']")')
            self.key('Escape', 27)
            self.scope_closed(trigger)
            self.scope_activate_key(' ')
            self.wait('document.querySelector("[data-scope-dropdown=' + kind + ']")')
            self.click('#chat-input')
            self.scope_closed(trigger, focus=False)
            self.scope_open(kind)
            if kind == 'factory':
                self.assertIn('전체 공장', self.text('[role=listbox] [role=option]:first-child'))
                self.assertTrue(self.browser.evaluate("document.querySelector('[role=listbox] [role=option]:first-child').getAttribute('aria-selected') === 'true'"))
                self.assertTrue(self.browser.evaluate("!!document.querySelector('#ees-factory-search')"))
                self.assertGreater(geometry['list']['scrollHeight'], geometry['list']['clientHeight'])
                self.assertIn(geometry['list']['overflow'], ('auto', 'scroll'))
                page_scroll = self.browser.evaluate('window.scrollY')
                point = self.browser.evaluate("(()=>{const r=document.querySelector('[data-scope-list=factory]').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()")
                self.browser.call('Input.dispatchMouseEvent', {'type': 'mouseWheel', **point,
                                  'deltaX': 0, 'deltaY': 140})
                self.wait("document.querySelector('[data-scope-list=factory]').scrollTop > 0")
                self.assertEqual(self.browser.evaluate('window.scrollY'), page_scroll)
                self.assertIn('담당', self.text('[data-action=choose_factory][data-factory-id=scope-factory-1]'))
                self.assertIn('참여', self.text('[data-action=choose_factory][data-factory-id=scope-factory-2]'))
                self.scope_search('공장 07')
                self.wait("!!document.querySelector('[data-action=choose_factory][data-factory-id=scope-factory-7]') && !document.querySelector('[data-action=choose_factory][data-factory-id=scope-factory-1]')")
                self.scope_search('')
                self.wait("document.querySelector('[data-action=choose_factory][data-factory-id=scope-factory-8]')")
                denied = '[data-action=choose_factory][data-factory-id=scope-factory-8]'
            else:
                self.assertFalse(self.browser.evaluate("!!document.querySelector('#ees-factory-search,[data-action=choose_factory]')"))
                denied = '[data-action=choose_system][data-system-id=FDC]'
            self.assertIn('권한 없음', self.text(denied))
            self.assertTrue(self.read(denied, 'disabled'))
            self.assertEqual(self.read(denied, 'ariaDisabled'), 'true')
            prior = self.text(trigger)
            denied_point = self.browser.evaluate('(()=>{const e=document.querySelector(' + json.dumps(denied) + ');e.scrollIntoView({block:"nearest"});const r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()')
            for event in ('mousePressed', 'mouseReleased'):
                self.browser.call('Input.dispatchMouseEvent', {'type': event, **denied_point,
                                  'button': 'left', 'clickCount': 1})
            self.assertEqual(self.text(trigger), prior)
            self.assertTrue(self.browser.evaluate('!!document.querySelector("[data-scope-dropdown]")'))
            option = '[data-action=choose_' + kind + '][data-' + kind + '-id=' + target + ']'
            self.click(option)
            self.scope_closed(trigger)
            self.wait('document.querySelector(' + json.dumps(trigger) + ').textContent.includes(' + json.dumps(expected) + ')')
            self.assertIsNotNone(self.refresh(), 'Selected scope did not finish its real service refresh')
            self.assertEqual(self.browser.evaluate('window.__eesNativeDraftV1.read()'), draft)
            self.assertEqual(self.browser.evaluate('location.pathname'), '/c/existing-chat')
            self.scope_open(kind)
            self.assertEqual(self.read(option, 'ariaSelected'), 'true')
            # EesIcon renders an image asset, not inline SVG. Assert the actual
            # selected check is loaded and visible, independently of its peer
            # scope icon or how many descendants the option contains.
            check_selector = option + ' img.ew-icon[src$="/9d8d5.svg"]'
            self.assertEqual(self.browser.evaluate('document.querySelectorAll(' + json.dumps(check_selector) + ').length'), 1)
            self.wait('document.querySelector(' + json.dumps(check_selector) + ')?.complete')
            check = self.browser.evaluate('''(()=>{const e=document.querySelector(''' + json.dumps(check_selector) + '''),
              r=e.getBoundingClientRect(),s=getComputedStyle(e),l=e.closest('[role=listbox]').getBoundingClientRect();
              return {src:e.getAttribute('src'),naturalWidth:e.naturalWidth,width:r.width,height:r.height,
                display:s.display,visibility:s.visibility,opacity:s.opacity,
                insideList:r.top>=l.top&&r.bottom<=l.bottom&&r.left>=l.left&&r.right<=l.right};})()''')
            self.assertGreater(check['naturalWidth'], 0, check)
            self.assertGreater(check['width'], 0, check)
            self.assertGreater(check['height'], 0, check)
            self.assertNotEqual(check['display'], 'none', check)
            self.assertEqual(check['visibility'], 'visible', check)
            self.assertGreater(float(check['opacity']), 0, check)
            self.assertTrue(check['insideList'], check)
            evidence[variant]['selectedCheck'] = check
            # Arrow movement is bounded by enabled options; Enter selects the
            # focused item and closes instead of submitting the chat.
            self.key('ArrowDown', 40)
            self.assertTrue(self.browser.evaluate('document.activeElement?.getAttribute("role") === "option" && !document.activeElement.disabled'))
            for _ in range(self.browser.evaluate('document.querySelectorAll("[role=listbox] [role=option]").length') + 1):
                self.key('ArrowDown', 40)
                self.assertTrue(self.browser.evaluate('document.activeElement?.getAttribute("role") === "option" && !document.activeElement.disabled'))
            self.key('ArrowUp', 38)
            self.assertTrue(self.browser.evaluate('document.activeElement?.getAttribute("role") === "option" && !document.activeElement.disabled'))
            self.scope_activate_key('Enter')
            self.scope_closed(trigger)
            self.assertIsNotNone(self.refresh())
        # The server's current grant changes metadata without changing the
        # selected scope. An already-open menu must stop showing the former
        # manager authority once that real response arrives.
        self.scope_open('system')
        self.command('save_access', user=self.scope_admin,
                     access_id=self.scope_apc_grant['access_id'],
                     expected_revision=self.scope_apc_grant['revision'],
                     principal_kind='user', principal_id=self.server.user['id'],
                     system_id='APC', factory_id='*', roles=['participant'])
        self.assertIsNotNone(self.refresh())
        self.scope_closed('#ees-work-system-trigger', focus=False)
        updated = self.scope_http_state()
        self.assertFalse(updated['capabilities']['can_author'])
        self.assertEqual(next(item['role'] for item in updated['scope_options']['systems']
                              if item['id'] == 'APC'), 'participant')
        self.scope_api_evidence['after_permission_change'] = {
            'managed_systems': updated['capabilities']['managed_systems'],
            'scope_options': updated['scope_options'], 'open_dropdowns': 0}
        self.assertEqual(self.browser.evaluate('window.__eesNativeDraftV1.read()'), draft)
        self.assertEqual(self.server.completions, [])
        evidence['keyboard'] = self.browser.evaluate('window.__scopeKeyboardEvidence')
        self.assertTrue(any(row['type'] == 'keypress' and row['key'] == 'Enter' and row['trusted']
                            for row in evidence['keyboard']))
        directory = self.screenshot('source-scope-three-dropdowns')
        (directory / 'source-scope-three-dropdowns.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        (directory / 'source-scope-api-permissions.json').write_text(json.dumps(self.scope_api_evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def test_scope_change_delayed_reads_keep_draft_expansion_and_zero_loading(self):
        self.enable_native_menus()
        self.scope_catalog_fixture()
        self.author(name='범위 변경 보존 절차', jobs=1)
        frame_monitor.install(self)
        self.navigate('/c/existing-chat')
        self.wait("document.querySelector('#ees-work-entry [data-action=my_work]') && window.__eesNativeDraftV1?.ready()")
        self.open_sidebar()
        self.assertIsNotNone(self.refresh())
        self.fill('#chat-input', '범위 변경 중에도 그대로인 문장')
        draft = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        self.wait("document.querySelector('#ees-work-entry .ew-workflows details')")
        group = '#ees-work-entry .ew-workflows details'
        if self.read(group, 'open'):
            self.click(group + ' > summary')
        self.assertFalse(self.read(group, 'open'))
        self.delay_workspace_reads()
        frame_monitor.guard_loading(self)
        labels = []
        for label, kind, target in (
                ('scope-factory-first', 'factory', 'scope-factory-1'),
                ('scope-factory-second', 'factory', 'scope-factory-2'),
                ('scope-all-factories', 'factory', ''),
                ('scope-system-apc', 'system', 'APC'),
                ('scope-system-ems', 'system', 'EMS')):
            trigger, _ = self.scope_open(kind)
            start = len(self.server.navigation_reads)
            frame_monitor.mark(self, label)
            self.click('[data-action=choose_' + kind + '][data-' + kind + '-id="' + target + '"]')
            self.scope_closed(trigger)
            self.wait_delayed_reads(start)
            labels.append(label)
            self.assertEqual(self.browser.evaluate('window.__eesNativeDraftV1.read()'), draft)
            self.assertEqual(self.browser.evaluate('location.pathname'), '/c/existing-chat')
        self.assertFalse(self.read(group, 'open'), 'Range selection reset the collapsed workflow group')
        # A new menu replaces the old one, and changing screens closes it.
        self.scope_open('system')
        self.scope_open('factory')
        self.click('[data-action=mode][data-mode=author]')
        self.wait('!document.querySelector("[data-scope-dropdown]")')
        self.wait("document.querySelector('#ees-work-designer')")
        self.scope_open('system')
        start = len(self.server.navigation_reads)
        frame_monitor.mark(self, 'scope-workspace-system-apc')
        self.click('[data-action=choose_system][data-system-id=APC]')
        self.scope_closed('#ees-work-system-trigger')
        self.wait_delayed_reads(start)
        labels.append('scope-workspace-system-apc')
        self.delayed_step('scope-native-skills', '[data-action=native_open][data-native-id=skills]',
                          "location.pathname === '/workspace/skills' && document.querySelector('#workspace-container input')",
                          paths=('workspace',))
        labels.append('scope-native-skills')
        self.scope_open('system')
        self.assertFalse(self.browser.evaluate("!!document.querySelector('#ees-work-site-trigger')"))
        start = len(self.server.navigation_reads)
        frame_monitor.mark(self, 'scope-native-system-ems')
        self.click('[data-action=choose_system][data-system-id=EMS]')
        self.scope_closed('#ees-work-system-trigger')
        self.wait_delayed_reads(start, paths=('workspace',))
        self.assertEqual(self.browser.evaluate('location.pathname'), '/workspace/skills')
        self.assertIn('EMS', self.text('#ees-work-system-trigger'))
        labels.append('scope-native-system-ems')
        self.delayed_step('scope-native-return', '#ees-work-entry [data-action=procedures]',
                          "location.pathname === '/c/existing-chat' && document.querySelector('#ees-work-designer')")
        labels.append('scope-native-return')
        # A changed server-provided catalog must invalidate an already open
        # list; it may not keep old options interactive until the next click.
        self.scope_open('system')
        self.command('save_factory', factory_id='scope-factory-1', system_id='EMS',
                     expected_revision=1, name='서버에서 바뀐 합성 공장 01')
        start = len(self.server.navigation_reads)
        frame_monitor.mark(self, 'scope-server-catalog-change')
        self.browser.evaluate('void window.__eesNativeWorkV1.refresh()')
        self.wait_delayed_reads(start)
        self.wait('!document.querySelector("[data-scope-dropdown]")')
        self.assertEqual(self.read('#ees-work-system-trigger', 'ariaExpanded'), 'false')
        labels.append('scope-server-catalog-change')
        self.assertEqual(self.browser.evaluate('window.__eesNativeDraftV1.read()'), draft)
        self.assertEqual(self.server.completions, [])
        evidence = frame_monitor.collect(self, labels=labels)
        evidence['reads'] = self.server.navigation_reads
        evidence['scope'] = 'A2 first-time scope selections, both real workspace and operations HTTP responses delayed 1000ms, physical browser input, unchanged Native draft and collapsed navigation.'
        directory = self.screenshot('source-scope-delayed-navigation')
        (directory / 'source-scope-delayed-frames.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        frame_monitor.assert_clean(self, evidence, labels=labels)

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
        keyboard = self.browser.evaluate('window.__scopeKeyboardEvidence || null')
        if keyboard is not None:
            (directory / (self._testMethodName + '-failure-keyboard.json')).write_text(
                json.dumps(keyboard, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def step(self, label, selector, condition):
        frame_monitor.mark(self, label)
        self.click(selector)
        self.wait(condition)
        frame_monitor.collect(self, labels=(label,))

    def delay_workspace_reads(self):
        """Delay both real service GET responses, not product timers/state."""
        original = NativeUIHandler.do_GET
        server = self.server
        server.navigation_reads = []

        def delayed(handler):
            path = urlparse(handler.path).path
            if handler.server is not server or path not in (
                    '/api/ees-work/workspace', '/api/ees-work/operations'):
                return original(handler)
            record = {'path': path, 'query': handler.path, 'started': time.monotonic(),
                      'delay_ms': 1000, 'completed': False}
            server.navigation_reads.append(record)
            time.sleep(1)
            record['released'] = time.monotonic()
            try:
                return original(handler)
            finally:
                record['completed'] = True
                record['finished'] = time.monotonic()

        fixture = patch.object(NativeUIHandler, 'do_GET', delayed)
        fixture.start()
        self.addCleanup(fixture.stop)

    def wait_delayed_reads(self, start, paths=('workspace', 'operations')):
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            reads = self.server.navigation_reads[start:]
            if (all(any(row['path'].endswith('/' + path) and row['completed'] for row in reads)
                    for path in paths) and all(row['completed'] for row in reads)):
                # Include paints after the last HTTP response was released.
                count = self.browser.evaluate('window.__eesSourceFrameEvidence.samples.length')
                self.wait('window.__eesSourceFrameEvidence.samples.length >= ' + str(count + 3))
                return
            time.sleep(.025)
        self.fail('Delayed response coverage incomplete: ' + repr(self.server.navigation_reads[start:]))

    def delayed_step(self, label, selector, condition, paths=('workspace', 'operations')):
        start = len(self.server.navigation_reads)
        self.step(label, selector, condition)
        self.wait_delayed_reads(start, paths)

    def test_delayed_navigation_never_replaces_loaded_menu_or_panel_with_loading(self):
        self.enable_native_menus()
        workflow_id = self.author(name='지연 응답 이동 검증 절차', jobs=2)
        self.start(workflow_id)
        frame_monitor.install(self)
        self.navigate('/c/existing-chat')
        self.wait("document.querySelector('#ees-work-entry [data-action=my_work]') && document.querySelector('#ees-work-content') && window.__eesNativeDraftV1?.ready()")
        self.open_sidebar()
        # Warm each destination once. First acquisition may show a placeholder;
        # every subsequent route transition below must use retained work data.
        self.step('warm-procedures', '[data-action=mode][data-mode=author]',
                  "document.querySelector('#ees-work-designer [data-author-action=create]')")
        self.step('warm-my-work', '[data-action=mode][data-mode=work]',
                  "document.querySelector('#ees-work-panel .ew-panel-header strong')?.textContent === '내 업무'")
        self.assertIsNotNone(self.refresh(), 'Initial workspace/operations refresh did not complete')
        self.wait("document.querySelector('#ees-work-entry [data-action=my_work]') && document.querySelector('#ees-work-content .ew-todo, #ees-work-content .ew-my-work-empty')")
        self.delay_workspace_reads()
        frame_monitor.guard_loading(self)
        labels = []

        for native in ('skills', 'tools', 'models'):
            for destination in ('procedures', 'my-work'):
                label = native + '-to-' + destination
                enter = label + '-enter-workspace'
                self.delayed_step(enter, '[data-action=mode][data-mode=author]',
                                  "document.querySelector('#ees-work-designer')")
                labels.append(enter)
                native_label = label + '-native'
                self.delayed_step(native_label, '[data-action=native_open][data-native-id=' + native + ']',
                                  'location.pathname === ' + json.dumps('/workspace/' + native)
                                  + ' && !!document.querySelector("#workspace-container input")',
                                  paths=('workspace',))
                labels.append(native_label)
                selector = ('[data-action=procedures]' if destination == 'procedures'
                            else '[data-action=mode][data-mode=work]')
                condition = ("document.querySelector('#ees-work-designer [data-author-action=create]')"
                             if destination == 'procedures' else
                             "document.querySelector('#ees-work-panel .ew-panel-header strong')?.textContent === '내 업무'")
                self.delayed_step(label, '#ees-work-entry ' + selector,
                                  "location.pathname === '/c/existing-chat' && (" + condition + ')')
                labels.append(label)

        self.step('delayed-chat-list', '[data-action=chats]',
                  "[...document.querySelectorAll('a[href=\"/c/other-chat\"]')].some(e=>e.getBoundingClientRect().height > 0)")
        labels.append('delayed-chat-list')
        self.delayed_step('delayed-chat-switch', 'a[href="/c/other-chat"]',
                          "location.pathname === '/c/other-chat' && window.__eesNativeDraftV1?.ready()")
        labels.append('delayed-chat-switch')
        self.delayed_step('delayed-new-chat', '[data-action=new_chat]',
                          "location.pathname === '/' && window.__eesNativeDraftV1?.ready()")
        labels.append('delayed-new-chat')
        self.step('delayed-chat-list-return', '[data-action=chats]',
                  "[...document.querySelectorAll('a[href=\"/c/existing-chat\"]')].some(e=>e.getBoundingClientRect().height > 0)")
        labels.append('delayed-chat-list-return')
        self.delayed_step('delayed-existing-return', 'a[href="/c/existing-chat"]',
                          "location.pathname === '/c/existing-chat' && window.__eesNativeDraftV1?.ready()")
        labels.append('delayed-existing-return')

        evidence = frame_monitor.collect(self, labels=labels)
        evidence['scope'] = ('Same assertions for baseline 42cc756 and candidate; real compiled frontend, '
                             'physical CDP clicks, temporary production workflow service; both workspace '
                             'and operations HTTP GETs delayed by 1000ms; no DOM masking or expected failure.')
        evidence['reads'] = self.server.navigation_reads
        evidence['counts'] = {label: {
            'frames': sum(row['label'] == label for row in evidence['samples']),
            'menu_loading': sum(row['label'] == label and bool(row['menuLoading']) for row in evidence['samples']),
            'panel_loading': sum(row['label'] == label and bool(row['panelLoading']) for row in evidence['samples'])}
            for label in labels}
        directory = self.screenshot('source-shell-delayed-navigation-final')
        (directory / 'source-shell-delayed-navigation-frames.json').write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        self.assertTrue(self.server.navigation_reads)
        for row in self.server.navigation_reads:
            self.assertGreaterEqual(row['released'] - row['started'], .99)
        frame_monitor.assert_clean(self, evidence, labels=labels)
        self.assertEqual(self.server.completions, [], 'Navigation must not submit a conversation')

    def test_background_refresh_and_native_return_keep_draft_nodes_expansion_and_scroll(self):
        self.enable_native_menus()
        workflow_id = self.author(name='증분 갱신 보존 절차', jobs=2)
        saved = self.state(workflow_id=workflow_id)['workflow']
        frame_monitor.install(self)
        self.navigate('/c/existing-chat')
        self.wait("document.querySelector('#ees-work-entry [data-action=my_work]') && window.__eesNativeDraftV1?.ready()")
        self.open_sidebar()
        self.fill('#chat-input', '새로 받는 동안 그대로 둘 개인 질문')
        composer = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        self.click('[data-action=mode][data-mode=author]')
        selector = '[data-author-action=open][data-id="' + workflow_id + '"]'
        self.wait('document.querySelector(' + json.dumps(selector) + ')')
        self.click(selector)
        self.wait("document.querySelector('[data-author-action=tab][data-tab=rules]')")
        self.click('[data-author-action=tab][data-tab=rules]')
        self.click('.ew-author-rule-policy > summary')
        field = '#ew-author-policies [name=completion_notes]'
        self.fill(field, '자동 갱신 중에도 유지할 미저장 완료 설명')
        self.wait("document.querySelector('.ew-author-rule-policy')?.open")
        # A real wheel gesture creates a nonzero scroll position. Saving DOM
        # references below only observes identity; it never pins/masks nodes.
        point = self.browser.evaluate("(()=>{const r=document.querySelector('.ew-author-scroll').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()")
        self.browser.call('Input.dispatchMouseEvent', {'type': 'mouseWheel', **point,
                          'deltaX': 0, 'deltaY': 120})
        self.wait("document.querySelector('.ew-author-scroll').scrollTop > 20")
        self.browser.evaluate("""new Promise(resolve=>{let previous=-1,stable=0;
          function check(){const top=document.querySelector('.ew-author-scroll').scrollTop;
            stable=top===previous?stable+1:0;previous=top;
            if(stable>=3)return resolve(top);requestAnimationFrame(check);}check();})""")
        self.browser.evaluate("""window.__retainedWorkNodes={
          field:document.querySelector('#ew-author-policies [name=completion_notes]'),
          detail:document.querySelector('.ew-author-rule-policy'),
          scroll:document.querySelector('.ew-author-scroll')};""")
        before = self.browser.evaluate("({scroll:window.__retainedWorkNodes.scroll.scrollTop,value:window.__retainedWorkNodes.field.value,open:window.__retainedWorkNodes.detail.open})")
        self.delay_workspace_reads()
        frame_monitor.guard_loading(self)

        # A real service mutation by another author changes the shared list.
        # The editor remains dirty and must neither lose its nodes nor save.
        other = self.command('create_workflow', name='뒤에서 추가된 새 절차', system_id='EMS')
        mark = len(self.server.navigation_reads)
        frame_monitor.mark(self, 'changed-background-refresh')
        self.browser.evaluate('void window.__eesNativeWorkV1.refresh()')
        self.wait_delayed_reads(mark)
        self.wait('document.querySelector(' + json.dumps('[data-action=workflow][data-workflow-id="' + other['workflow_id'] + '"]') + ')?.textContent.includes("뒤에서 추가된 새 절차")')

        def assert_preserved(label, *, same_nodes=True):
            observed = self.browser.evaluate("""(()=>{const old=window.__retainedWorkNodes,
              field=document.querySelector('#ew-author-policies [name=completion_notes]'),
              detail=document.querySelector('.ew-author-rule-policy'),scroll=document.querySelector('.ew-author-scroll');
              return {fieldSame:field===old.field,detailSame:detail===old.detail,scrollSame:scroll===old.scroll,
                value:field?.value,open:detail?.open,scroll:scroll?.scrollTop};})()""")
            if same_nodes:
                self.assertTrue(observed['fieldSame'], label + ': unchanged draft field was replaced')
                self.assertTrue(observed['detailSame'], label + ': expanded section was replaced')
                self.assertTrue(observed['scrollSame'], label + ': scroll container was replaced')
            self.assertEqual(observed['value'], before['value'], label)
            self.assertEqual(observed['open'], before['open'], label)
            self.assertAlmostEqual(observed['scroll'], before['scroll'], delta=1, msg=label)
            self.assertEqual(self.browser.evaluate('window.__eesNativeDraftV1.read()'), composer)
            return observed

        refreshed = assert_preserved('background refresh')
        self.delayed_step('preservation-native-skills', '[data-action=native_open][data-native-id=skills]',
                          "location.pathname === '/workspace/skills' && document.querySelector('#workspace-container input')",
                          paths=('workspace',))
        self.delayed_step('preservation-native-return', '#ees-work-entry [data-action=procedures]',
                          "location.pathname === '/c/existing-chat' && document.querySelector('#ew-author-policies [name=completion_notes]')")
        returned = assert_preserved('Native return')
        self.delayed_step('preservation-my-work', '[data-action=mode][data-mode=work]',
                          "document.querySelector('#ees-work-panel .ew-panel-header strong')?.textContent === '내 업무'")
        self.delayed_step('preservation-author-return', '[data-action=mode][data-mode=author]',
                          "document.querySelector('#ew-author-policies [name=completion_notes]')")
        # Work mode deliberately mounts a different panel. Returning must
        # restore editor state and position, rather than keep its DOM identity.
        work_returned = assert_preserved('Work mode return', same_nodes=False)
        self.assertEqual(self.state(workflow_id=workflow_id)['workflow'], saved)
        self.assertEqual(self.server.completions, [])
        evidence = frame_monitor.collect(self, labels=('changed-background-refresh',
                                         'preservation-native-skills', 'preservation-native-return',
                                         'preservation-my-work', 'preservation-author-return'))
        evidence['preservation'] = {'before': before, 'refreshed': refreshed, 'returned': returned,
                                    'work_returned': work_returned,
                                    'updated_workflow_id': other['workflow_id'],
                                    'saved_revision': saved['revision']}
        evidence['reads'] = self.server.navigation_reads
        directory = self.screenshot('source-shell-delayed-preservation-final')
        (directory / 'source-shell-delayed-preservation-frames.json').write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        frame_monitor.assert_clean(self, evidence)

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
        frame_monitor.guard_loading(self)
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
        evidence['ees_loading_after_initial'] = sum(
            item['loadingGuard'] and bool(item['menuLoading'] or item['panelLoading'])
            for item in evidence['samples'])
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
