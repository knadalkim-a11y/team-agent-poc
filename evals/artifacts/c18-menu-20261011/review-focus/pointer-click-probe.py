import json
import unittest
from test_ees_work_figma_authoring_native import FigmaAuthoringNativeTests

class PointerProbe(FigmaAuthoringNativeTests):
    def test_pointer_probe(self):
        self.native_menu_fixture()
        self.fill('#chat-input', '관리자 설정 초점 검사 전 개인 질문')
        draft = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        self.click('[data-action=mode][data-mode=author]')
        self.click('[data-author-action=create]')
        self.fill('#ew-procedure-name', '초점 검사 후에도 보존할 미저장 절차')
        reference = self.browser.evaluate('window.__eesNativeWorkV1.captureReference()')
        self.click('[data-action=native_open][data-native-id=admin]')
        self.wait("document.querySelector('#settings-tabs-container [role=tab][aria-controls=tab-admin-general][aria-selected=true]') && document.querySelector('[role=dialog][aria-modal=true] input[type=text][placeholder*=\"localhost:3000\"]') && document.querySelector('#ees-work-entry [data-action=procedures]')")
        observe = """(()=>{
          const modal=document.querySelector('[role=dialog][aria-modal=true]:has(#settings-tabs-container)');
          const controls=[...modal.querySelectorAll('a[href],button,input,select,textarea,[tabindex]')].filter(e=>e.tabIndex>=0&&!e.matches(':disabled')&&!e.closest('[inert]')&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden');
          const describe=e=>({tag:e?.tagName,id:e?.id||'',name:e?.name||'',role:e?.getAttribute('role'),label:e?.getAttribute('aria-label')||'',text:e?.textContent?.trim().slice(0,80)||''});
          const active=document.activeElement,menu=document.querySelector('#ees-work-entry');
          return {path:location.pathname,dialog:!!modal,contained:modal.contains(active),menuFocused:menu.contains(active),menuInert:!!menu.closest('[inert]'),active:describe(active),index:controls.indexOf(active),controls:controls.map(describe)};
        })()"""
        # Establish focus with a real pointer, then use trusted browser Tab
        # events. DOM dispatchEvent/focus() cannot prove Native's focus trap.
        self.click('[role=dialog] input[type=text][placeholder*="localhost:3000"]')
        initial = self.browser.evaluate(observe)
        self.assertTrue(initial['contained'])
        self.assertGreater(len(initial['controls']), 2)
        sequence = []
        for direction, modifiers in (('Tab', 0), ('Shift+Tab', 8)):
            for index in range(len(initial['controls']) * 2 + 4):
                self.key('Tab', 9, modifiers)
                record = self.browser.evaluate(observe)
                record.pop('controls')
                record.update(direction=direction,step=index+1)
                sequence.append(record)
        menu_pointer = self.browser.evaluate("""(()=>{const e=document.querySelector('#ees-work-entry [data-action=procedures]'),r=e.getBoundingClientRect(),x=r.x+r.width/2,y=r.y+r.height/2,hit=document.elementFromPoint(x,y);return {point:{x,y},reachable:e.contains(hit),hit:{tag:hit?.tagName,id:hit?.id,classes:hit?.className,role:hit?.getAttribute('role')},menuInert:!!e.closest('[inert]')};})()""")
        directory = self.screenshot('menu-c18-admin-keyboard-focus')
        (directory / 'menu-c18-admin-keyboard-focus.json').write_text(json.dumps({
            'scope': 'actual compiled Open WebUI 0.11.3 modal and trusted Chrome CDP keyboard/pointer; temporary workflow SQLite and synthetic Native session/capability responses; not real company authentication or ACL verification',
            'initial': initial, 'sequence': sequence, 'menu_pointer': menu_pointer,
        }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        self.assertTrue(all(item['dialog'] and item['contained'] and not item['menuFocused']
                            for item in sequence), sequence)
        for direction in ('Tab', 'Shift+Tab'):
            visited = [item['index'] for item in sequence if item['direction'] == direction]
            self.assertIn(0, visited)
            self.assertIn(len(initial['controls']) - 1, visited)
            self.assertLess(len(set(visited)), len(visited), 'Expected a complete focus cycle')
            boundary = (len(initial['controls']) - 1, 0) if direction == 'Tab' else (0, len(initial['controls']) - 1)
            self.assertIn(boundary, list(zip(visited, visited[1:])))
        # Pointer navigation remains available while the modal is open; it
        # closes settings and restores the unsaved procedure and chat draft.
        self.click('#ees-work-entry [data-action=procedures]')
        self.wait("location.pathname === '/c/existing-chat' && window.__eesNativeDraftV1?.ready() && document.querySelector('#ew-procedure-name') && !document.querySelector('#settings-tabs-container')")
        self.assertEqual(self.read('#ew-procedure-name', 'value'), '초점 검사 후에도 보존할 미저장 절차')
        self.assertEqual(self.browser.evaluate('window.__eesNativeDraftV1.read()'), draft)
        self.assert_reference_preserved(reference)
        self.assertEqual(self.server.completions, [])
        self.assertEqual(self.state()['workflows'], [])
        self.screenshot('menu-c18-admin-keyboard-menu-returned')

if __name__ == "__main__":
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([PointerProbe("test_pointer_probe")]))
    raise SystemExit(not result.wasSuccessful())
