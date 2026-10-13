"""Q1 actual built Native geometry and private panel preferences.

Native frontend, assets and workspace SQLite are real. Sessions and source data
are synthetic here; the complete app/account gates test actual Native login.
"""
from copy import deepcopy
import json
import time

from ees_work_integrated_fixture import IntegratedNativeCase
import ees_source_frame_monitor as frame_monitor


class FigmaLayoutNativeTests(IntegratedNativeCase):
    def wait_saved_width(self, width):
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            if self.state().get('ui_state',{}).get('state',{}).get('selection',{}).get('panel_width')==width:return
            time.sleep(.025)
        self.fail('Private panel width did not persist: '+str(width))

    def viewport(self, width, height=768):
        self.browser.call('Emulation.setDeviceMetricsOverride', {
            'width': width, 'height': height, 'deviceScaleFactor': 1, 'mobile': False})
        self.wait('innerWidth === ' + str(width))
        self.wait("document.querySelector('[data-ees-source-sidebar]')?.dataset.compact === " + json.dumps(str(width < 1440).lower()))
        self.wait("Math.abs(document.querySelector('[data-ees-source-shell]').getBoundingClientRect().width - "+str(width)+") < .01")

    def geometry(self):
        return self.browser.evaluate("""(()=>{
          const box=s=>{const e=document.querySelector(s),r=e?.getBoundingClientRect();return r?{x:r.x,y:r.y,width:r.width,height:r.height,bottom:r.bottom}:null;};
          return {viewport:[innerWidth,innerHeight],sidebar:box('#sidebar'),panel:box('.ees-panel-region'),chat:box('.ees-chat-region'),header:box('#ees-work-context'),headerTitle:box('#ees-work-context .ees-context-title'),message:box('.message-listitem'),composer:box('#message-input-container'),footer:box('#ees-work-panel>.ew-job-actions'),overflow:document.documentElement.scrollWidth>innerWidth,overlay:document.querySelector('.ees-panel-region').dataset.overlay};
        })()""")

    def evidence(self, label):
        directory=self.screenshot(label)
        (directory/(label+'.json')).write_text(json.dumps(self.geometry(),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

    def resize_keyboard(self, key, code):
        self.click('[data-ees-panel-resize]')
        self.key(key,code)

    def test_q1_geometry_reading_width_footer_and_baseline_overlay(self):
        key=self.author(fields=[{'id':'field-'+str(i),'name':'확인 값 '+str(i),'type':'text'} for i in range(18)],jobs=1)
        run=self.start(key);self.open_run(key,run)
        for width,sidebar in [(1920,256),(1536,256),(1366,56),(1280,56)]:
            self.viewport(width)
            geometry=self.geometry()
            self.assertEqual(geometry['sidebar']['width'],sidebar)
            self.assertEqual(geometry['panel']['width'],480)
            self.assertEqual(geometry['chat']['width'],width-sidebar-480)
            self.assertEqual(geometry['overlay'],'false')
            self.assertFalse(geometry['overflow'])
            self.assertEqual(geometry['header']['height'],48)
            self.assertAlmostEqual(geometry['headerTitle']['x']-geometry['header']['x'],24,delta=1/64)
            self.assertAlmostEqual(geometry['composer']['width'],min(760,geometry['chat']['width']-48),delta=1)
            self.assertLessEqual(geometry['message']['width'],min(760,geometry['chat']['width']-48)+1)
            self.assertLessEqual(geometry['footer']['bottom'],768)
            self.assertGreaterEqual(geometry['footer']['height'],50)
            self.assertTrue(self.browser.evaluate("document.querySelector('#ees-work-content').scrollHeight > document.querySelector('#ees-work-content').clientHeight"))
            if width in (1920,1366):self.evidence('q1-'+str(width)+'x768')
        self.click('[data-ees-sidebar-toggle]')
        self.assertEqual(self.geometry()['sidebar']['width'],256)
        self.assertEqual(self.geometry()['overlay'],'true')
        self.click('[data-ees-sidebar-toggle]')
        # Widening by itself does not activate the unresolved overlay policy.
        self.resize_keyboard('End',35)
        geometry=self.geometry()
        self.assertEqual(geometry['sidebar']['width'],56)
        self.assertEqual(geometry['panel']['width'],720)
        # The flex remainder may differ by one observed 1/64 CSS pixel.
        # Keep exact fixed widths and check adjoining edges and overflow too.
        self.assertAlmostEqual(geometry['chat']['width'],504,delta=1/64)
        self.assertAlmostEqual(geometry['chat']['x']+geometry['chat']['width'],geometry['panel']['x'],delta=1/64)
        self.assertAlmostEqual(geometry['panel']['x']+geometry['panel']['width'],1280,delta=1/64)
        self.assertEqual(geometry['overlay'],'false')
        self.assertFalse(geometry['overflow'])
        self.evidence('q1-wide-panel-1280x768')
        self.resize_keyboard('Home',36)
        self.assertEqual(self.geometry()['panel']['width'],400)
        self.viewport(1095)
        self.assertEqual(self.geometry()['overlay'],'true')
        self.assertEqual(self.geometry()['chat']['width'],1039)
        self.click('[data-action=close_panel]')
        self.wait("document.querySelector('.ees-panel-region').hidden")
        self.click('[data-action=open_panel]')
        self.wait("!document.querySelector('.ees-panel-region').hidden")
        self.evidence('q1-overlay-close-reopen')

    def test_q1_physical_drag_restores_per_actor_width_and_contrast(self):
        handle=self.browser.evaluate("(()=>{const r=document.querySelector('[data-ees-panel-resize]').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+100};})()")
        self.browser.call('Input.dispatchMouseEvent',{'type':'mousePressed',**handle,'button':'left','buttons':1,'clickCount':1})
        self.browser.call('Input.dispatchMouseEvent',{'type':'mouseMoved','x':handle['x']-160,'y':handle['y'],'button':'left','buttons':1})
        self.browser.call('Input.dispatchMouseEvent',{'type':'mouseReleased','x':handle['x']-160,'y':handle['y'],'button':'left','buttons':0,'clickCount':1})
        self.wait("document.querySelector('.ees-panel-region').getBoundingClientRect().width === 640")
        self.wait_saved_width(640)
        actor_a=dict(self.server.user)
        self.navigate('/c/existing-chat');self.wait("document.querySelector('.ees-panel-region')?.getBoundingClientRect().width===640")
        self.users['other-user']={**deepcopy(actor_a),'id':'other-user','name':'Other synthetic user'}
        self.server.user=self.users['other-user']
        self.navigate('/');self.wait("document.querySelector('.ees-panel-region')?.getBoundingClientRect().width===480")
        self.resize_keyboard('Home',36)
        self.wait_saved_width(400)
        self.server.user=actor_a
        self.navigate('/c/existing-chat');self.wait("document.querySelector('.ees-panel-region')?.getBoundingClientRect().width===640")
        ratios=self.browser.evaluate("""(()=>{
          const style=getComputedStyle(document.querySelector('#ees-work-panel')),hex=n=>style.getPropertyValue(n).trim();
          const lum=h=>{const c=h.replace('#','').match(/../g).map(x=>parseInt(x,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return c[0]*.2126+c[1]*.7152+c[2]*.0722;};
          const ratio=(a,b)=>(Math.max(lum(a),lum(b))+.05)/(Math.min(lum(a),lum(b))+.05);
          return {amber:hex('--ees-status-attention'),green:hex('--ees-status-success'),attention:ratio(hex('--ees-status-attention'),hex('--ees-status-attention-bg')),success:ratio(hex('--ees-status-success'),hex('--ees-status-success-bg')),danger:ratio(hex('--ees-status-danger'),hex('--ees-status-danger-bg')),body:ratio(hex('--ees-text-primary'),'#ffffff'),secondary:ratio(hex('--ees-text-secondary'),'#ffffff'),secondaryPanel:ratio(hex('--ees-text-secondary'),hex('--ees-surface-panel')),meta:ratio(hex('--ees-text-tertiary'),'#fafafa'),metaPanel:ratio(hex('--ees-text-tertiary'),hex('--ees-surface-panel'))};
        })()""")
        self.assertEqual(ratios['amber'],'#96590c');self.assertEqual(ratios['green'],'#2a744c')
        for name in ('attention','success','danger','body','secondary','secondaryPanel','meta','metaPanel'):self.assertGreaterEqual(ratios[name],4.5,name)
        directory=self.screenshot('q1-private-width-640')
        (directory/'q1-contrast.json').write_text(json.dumps(ratios,indent=2)+'\n',encoding='utf-8')

    def test_c18_panel_cards_input_hover_and_keyboard_focus(self):
        self.author(name='화면 색상 검증 절차', jobs=1)
        self.browser.evaluate('window.__eesNativeWorkV1.refresh()')
        self.click('[data-action=mode][data-mode=author]')
        self.wait("document.querySelector('.ew-author-list>button')")

        def background(selector):
            return self.browser.evaluate('getComputedStyle(document.querySelector(' + json.dumps(selector) + ')).backgroundColor')

        def hover(selector):
            point = self.browser.evaluate('(()=>{const r=document.querySelector(' + json.dumps(selector) + ').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()')
            self.browser.call('Input.dispatchMouseEvent', {'type': 'mouseMoved', **point})
            self.wait('document.querySelector(' + json.dumps(selector) + ').matches(":hover")')

        observed = {name: background(selector) for name, selector in {
            'panel': '#ees-work-panel', 'author': '#ees-work-designer',
            'card': '.ew-author-list', 'input': '#ew-author-search',
            'chat': '#chat-container #chat-pane'}.items()}
        self.assertEqual(observed, {'panel': 'rgb(243, 243, 245)', 'author': 'rgb(243, 243, 245)',
            'card': 'rgb(255, 255, 255)', 'input': 'rgb(255, 255, 255)', 'chat': 'rgb(255, 255, 255)'})
        hover('.ew-author-list>button')
        observed['cardHover'] = background('.ew-author-list>button')
        self.assertEqual(observed['cardHover'], 'rgb(243, 243, 245)')
        hover('#ees-work-panel>.ew-panel-header .ew-icon-button')
        observed['headerHover'] = background('#ees-work-panel>.ew-panel-header .ew-icon-button')
        self.assertEqual(observed['headerHover'], 'rgb(236, 236, 239)')
        self.click('#ew-author-search')
        self.key('Tab', 9)
        self.assertTrue(self.browser.evaluate("document.activeElement?.matches('.ew-author-list>button:focus-visible')"))
        observed['keyboardOutline'] = self.browser.evaluate('getComputedStyle(document.activeElement).outline')
        self.assertIn('solid', observed['keyboardOutline'])
        self.assertIn('2px', observed['keyboardOutline'])
        directory = self.screenshot('c18-panel-card-focus-desktop')
        (directory / 'c18-panel-computed.json').write_text(json.dumps(observed, indent=2) + '\n', encoding='utf-8')
        self.browser.call('Emulation.setDeviceMetricsOverride', {
            'width': 600, 'height': 768, 'deviceScaleFactor': 1, 'mobile': False})
        self.wait('innerWidth === 600')
        self.wait("document.querySelector('[data-ees-source-sidebar][data-compact=true]') && document.querySelector('[data-ees-sidebar-toggle]')?.getBoundingClientRect().width > 0")
        self.assertTrue(self.browser.evaluate("!!document.querySelector('[data-ees-source-sidebar] #sidebar-search-button')"))
        self.wait("document.querySelector('#ees-work-panel')")
        self.assertFalse(self.geometry()['overflow'])
        self.screenshot('c18-panel-card-narrow')

    def test_source_startup_root_and_existing_chat_reveal_only_after_ees_layout(self):
        # Retain the original test ID but replace the retired four-second body
        # gate contract: source chrome must be visible before slow business data.
        frame_monitor.install(self)
        results = {}
        for path in ('/', '/c/existing-chat'):
            self.server.delay_next_workspace = True
            self.server.workspace_response_started.clear()
            self.server.workspace_response_hold.clear()
            self.navigate(path)
            self.wait("document.querySelector('[data-ees-source-shell]') && document.querySelector('[data-ees-source-sidebar]') && document.querySelector('#chat-input.ProseMirror')")
            self.assertTrue(self.server.workspace_response_started.wait(timeout=2), "Held workspace read was not reached")
            self.assertEqual(self.browser.evaluate("getComputedStyle(document.body).visibility"), 'visible')
            self.assertFalse(self.browser.evaluate("!!document.querySelector('#ees-startup-gate,#ees-startup-style')"))
            self.assertFalse(self.browser.evaluate("!!document.documentElement.dataset.eesStartup"))
            self.server.workspace_response_hold.set()
            self.wait("window.__eesNativeWorkV1 && document.querySelector('#ees-work-entry') && document.querySelector('#ees-work-panel')")
            evidence = frame_monitor.collect(self, labels=('first-load',))
            frame_monitor.assert_clean(self, evidence, labels=('first-load',))
            results[path] = evidence
        self.assertIn('기존 대화 기록', self.text('body'))
        directory = self.screenshot('source-shell-first-loading')
        (directory / 'source-shell-first-loading-frames.json').write_text(
            json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def test_source_startup_missing_launcher_fails_open_with_native_chat_accessible(self):
        # Retain the old ID's failure-recovery protection. A missing right-panel
        # runtime must keep the *source* menu and real Native composer usable;
        # falling back to the retired Native sidebar is no longer acceptable.
        frame_monitor.install(self)
        self.browser.call('Network.setBlockedURLs', {'urls': ['*/_ees14/ees-work-launcher.js*']})
        self.addCleanup(lambda: self.browser.call('Network.setBlockedURLs', {'urls': []}))
        self.navigate('/c/existing-chat')
        self.wait("document.querySelector('[data-ees-source-shell]') && document.querySelector('[data-ees-source-sidebar]') && document.querySelector('#chat-input.ProseMirror')")
        self.assertEqual(self.browser.evaluate("getComputedStyle(document.querySelector('#chat-input')).visibility"), 'visible')
        self.assertFalse(self.browser.evaluate("!!document.querySelector('#ees-startup-gate,#ees-startup-style')"))
        self.assertFalse(self.browser.evaluate("!!window.__eesNativeWorkV1"))
        self.assertTrue(self.browser.evaluate("!!document.querySelector('#ees-work-entry')"))
        self.assertIn('기존 대화 기록', self.text('body'))
        self.fill('#chat-input', '실행 코드가 없어도 보존되는 개인 초안')
        self.assertIn('실행 코드가 없어도 보존되는 개인 초안', self.text('#chat-input'))
        evidence = frame_monitor.collect(self, labels=('first-load',))
        frame_monitor.assert_clean(self, evidence, labels=('first-load',))
        directory = self.screenshot('source-shell-missing-runtime')
        (directory / 'source-shell-missing-runtime-frames.json').write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
