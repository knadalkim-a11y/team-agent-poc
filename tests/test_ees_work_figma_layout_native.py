"""Actual built Native work/chat geometry and account-private chat preferences.

Native frontend, assets and workspace SQLite are real. Sessions and source data
are synthetic here; the complete app/account gates test actual Native login.
"""
from copy import deepcopy
import json
import time

from ees_work_integrated_fixture import IntegratedNativeCase
import ees_source_frame_monitor as frame_monitor


class FigmaLayoutNativeTests(IntegratedNativeCase):
    def wait_layout_motion(self):
        self.wait("!document.querySelector('[data-ees-source-shell]').getAnimations({subtree:true}).some(a=>a.effect?.target?.matches('#sidebar,.ees-chat-space,[data-ees-work-surface],[data-ees-chat-surface]'))")

    def wait_saved_width(self, width):
        deadline = time.monotonic() + 5
        saved = {}
        while time.monotonic() < deadline:
            saved = self.state()['ui_state']['state'].get('selection', {})
            if saved.get('chat_width') == width:
                return
            time.sleep(.025)
        self.fail(f'Private chat width not saved: {width}; observed {saved.get("chat_width")}')

    def viewport(self, width, height=768, *, overlay=None):
        self.browser.call('Emulation.setDeviceMetricsOverride', {
            'width': width, 'height': height, 'deviceScaleFactor': 1, 'mobile': False})
        self.wait(f"innerWidth === {width} && innerHeight === {height}")
        self.wait("document.querySelector('[data-ees-source-sidebar]')?.dataset.compact === " + json.dumps(str(width < 1440).lower()))
        if overlay:
            self.wait("document.querySelector('[data-ees-source-shell]')?.dataset.eesChatState === 'closed'")
        self.wait_layout_motion()

    def chat_state(self, state):
        self.wait("document.querySelector('[data-ees-source-shell]')?.dataset.eesChatState === " + json.dumps(state))
        self.wait_layout_motion()

    def geometry(self):
        return self.browser.evaluate("""(()=>{
          const box=s=>{const e=document.querySelector(s),r=e?.getBoundingClientRect();return r?{x:r.x,y:r.y,width:r.width,height:r.height,bottom:r.bottom,right:r.right}:null;};
          return {viewport:[innerWidth,innerHeight],sidebar:box('#sidebar'),work:box('[data-ees-work-surface]'),chat:box('[data-ees-chat-surface]'),header:box('#ees-work-context'),message:box('.message-listitem'),composer:box('#message-input-container'),footer:box('#ees-work-panel>.ew-job-actions'),overflow:document.documentElement.scrollWidth>innerWidth,state:document.querySelector('[data-ees-source-shell]').dataset.eesChatState};
        })()""")

    def evidence(self, label):
        directory=self.screenshot(label)
        (directory/(label+'.json')).write_text(json.dumps(self.geometry(),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

    def resize_keyboard(self, key, code, expected):
        self.wait("window.__eesNativeDraftV1?.ready?.()")
        self.click('[data-ees-chat-resize]')
        self.wait("document.activeElement?.matches('[data-ees-chat-resize]')")
        self.key(key,code)
        self.wait(f"Math.abs(document.querySelector('[data-ees-chat-surface]').getBoundingClientRect().width - {expected}) < 1")
        self.wait_layout_motion()

    def test_q1_geometry_reading_width_footer_and_baseline_overlay(self):
        key=self.author(fields=[{'id':'field-'+str(i),'name':'확인 값 '+str(i),'type':'text'} for i in range(18)],jobs=1)
        run=self.start(key);self.open_run(key,run)
        for width,height,sidebar,chat in ((1920,1080,256,560),(1536,864,256,560),(1366,768,56,480),(1280,768,56,480)):
            with self.subTest(width=width):
                self.viewport(width,height)
                self.chat_state('docked')
                geometry=self.geometry()
                sidebar_box,work,chat_box=geometry['sidebar'],geometry['work'],geometry['chat']
                self.assertAlmostEqual(sidebar_box['width'],sidebar,delta=1)
                self.assertAlmostEqual(sidebar_box['right'],work['x'],delta=1)
                self.assertAlmostEqual(work['width'],width-sidebar-chat,delta=1)
                self.assertAlmostEqual(work['right'],chat_box['x'],delta=1)
                self.assertAlmostEqual(chat_box['width'],chat,delta=1)
                self.assertAlmostEqual(chat_box['right'],width,delta=1)
                self.assertFalse(geometry['overflow'],geometry)
                for name in ('message','composer'):
                    box=geometry[name]
                    self.assertGreaterEqual(box['x'],chat_box['x']-1,name)
                    self.assertLessEqual(box['right'],width+1,name)
                self.assertLessEqual(geometry['footer']['bottom'],height)
                self.assertGreaterEqual(geometry['footer']['height'],40)
                if width in (1920,1366):self.evidence(f'q1-{width}x{height}')
        self.resize_keyboard('End',35,584)  # 1280 - 56 - 640
        self.resize_keyboard('Home',36,420)
        # Split threshold is *available* width, including actual nav width.
        self.viewport(1117)
        if self.geometry()['state']=='closed':
            self.click('[data-ees-chat-toggle]')
        self.chat_state('docked')
        self.viewport(1116)
        self.chat_state('docked')
        self.assertAlmostEqual(self.geometry()['work']['width'],640,delta=1)
        self.viewport(1115)
        if self.geometry()['state']=='closed':
            self.click('[data-ees-chat-toggle]')
        self.chat_state('overlay')
        self.assertAlmostEqual(self.geometry()['work']['width'],1115-56,delta=1)
        self.key('Escape',27)
        self.chat_state('closed')
        self.viewport(480,overlay=True)
        work=self.geometry()['work']
        self.assertAlmostEqual(work['width'],480-56,delta=1)
        self.assertFalse(self.geometry()['overflow'])
        self.evidence('q1-480x768-work')
        self.click('[data-ees-chat-toggle]')
        self.chat_state('overlay')
        self.assertTrue(self.browser.evaluate("document.querySelector('[data-ees-chat-surface]').contains(document.activeElement)"))
        self.assertTrue(self.browser.evaluate("document.querySelector('[data-ees-work-surface]').inert || !!document.querySelector('[data-ees-work-surface]').closest('[inert]')"))
        self.assertFalse(self.geometry()['overflow'])
        self.evidence('q1-480x768-chat')
        self.key('Escape',27)
        self.chat_state('closed')
        self.wait("document.activeElement?.matches('[data-ees-chat-toggle]')")

    def test_q1_physical_drag_restores_per_actor_width_and_contrast(self):
        self.viewport(1920,1080)
        self.chat_state('docked')
        initial=self.geometry()['chat']['width']
        self.assertAlmostEqual(initial,560,delta=1)
        handle=self.browser.evaluate("(()=>{const r=document.querySelector('[data-ees-chat-resize]').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+100};})()")
        self.browser.call('Input.dispatchMouseEvent',{'type':'mousePressed',**handle,'button':'left','buttons':1,'clickCount':1})
        self.browser.call('Input.dispatchMouseEvent',{'type':'mouseMoved','x':handle['x']-80,'y':handle['y'],'button':'left','buttons':1})
        self.browser.call('Input.dispatchMouseEvent',{'type':'mouseReleased','x':handle['x']-80,'y':handle['y'],'button':'left','buttons':0,'clickCount':1})
        self.wait_saved_width(640)
        actor_a=dict(self.server.user)
        self.navigate('/c/existing-chat');self.wait("document.querySelector('[data-ees-chat-surface]')?.getBoundingClientRect().width===640")
        self.users['other-user']={**deepcopy(actor_a),'id':'other-user','name':'Other synthetic user'}
        self.server.user=self.users['other-user']
        self.navigate('/');self.wait("document.querySelector('[data-ees-chat-surface]')?.getBoundingClientRect().width===560")
        self.resize_keyboard('Home',36,420)
        self.wait_saved_width(420)
        self.server.user=actor_a
        self.navigate('/c/existing-chat');self.wait("document.querySelector('[data-ees-chat-surface]')?.getBoundingClientRect().width===640")
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
        workflow_id = self.author(name='화면 색상 검증 절차', jobs=1)
        self.browser.evaluate('window.__eesNativeWorkV1.refresh()')
        self.click('[data-action=mode][data-mode=author]')
        self.wait("document.querySelector('.ew-author-list>button')")

        def background(selector):
            return self.browser.evaluate('getComputedStyle(document.querySelector(' + json.dumps(selector) + ')).backgroundColor')

        def hover(selector, expected_background):
            point = self.browser.evaluate('(()=>{const r=document.querySelector(' + json.dumps(selector) + ').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()')
            self.browser.call('Input.dispatchMouseEvent', {'type': 'mouseMoved', **point})
            self.wait('document.querySelector(' + json.dumps(selector) + ').matches(":hover")')
            # C3 interpolates hover colors for 120ms. Assert the endpoint once
            # computed style reaches it, not the first interpolated frame.
            self.wait('getComputedStyle(document.querySelector(' + json.dumps(selector) +
                      ')).backgroundColor === ' + json.dumps(expected_background))

        observed = {name: background(selector) for name, selector in {
            'panel': '#ees-work-panel', 'author': '#ees-work-designer',
            'card': '.ew-author-list', 'input': '#ew-author-search',
            'chat': '#chat-container #chat-pane'}.items()}
        # Work uses the authoring surface; white inputs and chat stay distinct.
        self.assertEqual(observed, {'panel': 'rgb(250, 250, 250)', 'author': 'rgb(250, 250, 250)',
            'card': 'rgba(0, 0, 0, 0)', 'input': 'rgb(255, 255, 255)', 'chat': 'rgb(255, 255, 255)'})
        hover('.ew-author-list>button', 'rgb(243, 243, 245)')
        observed['cardHover'] = background('.ew-author-list>button')
        self.assertEqual(observed['cardHover'], 'rgb(243, 243, 245)')
        observed['cardMotion'] = self.browser.evaluate("(()=>{const e=document.querySelector('.ew-author-list>button'),s=getComputedStyle(e);return {focusVisible:e.matches(':focus-visible'),property:s.transitionProperty,duration:s.transitionDuration,easing:s.transitionTimingFunction};})()")
        self.assertFalse(observed['cardMotion']['focusVisible'])
        self.assertEqual(observed['cardMotion']['property'].split(', '),
                         ['background-color', 'border-color', 'color', 'box-shadow'])
        self.assertEqual(observed['cardMotion']['duration'].split(', '), ['0.12s'] * 4)
        self.assertEqual(observed['cardMotion']['easing'],
                         ', '.join(['cubic-bezier(0.2, 0.8, 0.2, 1)'] * 4))
        hover('#ees-work-designer>header .ew-icon-button', 'rgb(236, 236, 239)')
        observed['headerHover'] = background('#ees-work-designer>header .ew-icon-button')
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

        # Exercise actual view changes, including the old task panel and tools,
        # so a later per-screen override cannot silently split the shared style.
        shared = {}

        def capture_style(label, tabs=None):
            self.browser.call('Input.dispatchMouseEvent', {'type': 'mouseMoved', 'x': 0, 'y': 0})
            if tabs:
                self.wait('getComputedStyle(document.querySelector(' + json.dumps(tabs) +
                          ').querySelector("button")).backgroundColor === "rgba(0, 0, 0, 0)"')
            result = self.browser.evaluate("""((selector)=>{
              const panel=document.querySelector('#ees-work-panel'),author=panel.querySelector('#ees-work-designer');
              const result={panel:getComputedStyle(panel).backgroundColor,author:author?getComputedStyle(author).backgroundColor:null};
              const nav=selector?document.querySelector(selector):null;
              if(nav){
                const active=nav.querySelector('[aria-selected=true],[aria-pressed=true]'),inactive=nav.querySelector('[aria-selected=false],[aria-pressed=false]');
                const read=element=>{const s=getComputedStyle(element);return {color:s.color,background:s.backgroundColor,font:s.fontSize,line:s.lineHeight,weight:s.fontWeight,height:element.getBoundingClientRect().height,paddingTop:s.paddingTop,paddingBottom:s.paddingBottom};};
                const underline=getComputedStyle(active,'::after');
                result.tabs={gap:getComputedStyle(nav).gap,active:read(active),inactive:read(inactive),underline:underline.backgroundColor,underlineHeight:underline.height};
              }
              return result;
            })(""" + json.dumps(tabs) + ')')
            self.assertEqual(result['panel'], 'rgb(250, 250, 250)', label)
            if result['author'] is not None:
                self.assertEqual(result['author'], result['panel'], label)
                self.assertEqual(background('#ees-work-designer>footer'), result['panel'], label)
            if tabs:
                # Task-detail tabs retain their compact style; the stage and
                # authoring pages use the larger primary navigation of mock 1.
                primary_tabs=label=='work-stage' or label.startswith('author-')
                self.assertEqual(result['tabs'], {
                    'gap':'24px' if primary_tabs else '20px',
                    'active': {'color': 'rgb(31, 32, 35)', 'background': 'rgba(0, 0, 0, 0)',
                               'font': '13px' if primary_tabs else '12px', 'line': '18px', 'weight': '500', 'height': 38 if primary_tabs else 36,
                               'paddingTop': '8px' if primary_tabs else '6px','paddingBottom':'12px' if primary_tabs else '10px'},
                    'inactive': {'color': 'rgb(92, 94, 101)', 'background': 'rgba(0, 0, 0, 0)',
                                 'font': '13px' if primary_tabs else '12px', 'line': '18px', 'weight': '400', 'height': 38 if primary_tabs else 36,
                                 'paddingTop': '8px' if primary_tabs else '6px','paddingBottom':'12px' if primary_tabs else '10px'},
                    'underline': 'rgb(47, 95, 152)', 'underlineHeight': '2px'}, label)
            self.assertFalse(self.geometry()['overflow'], label)
            shared[label] = result

        def capture_tab_focus(label, tabs):
            # Enter keyboard modality with real Tab/Shift+Tab. The focus outline
            # stays inside the tab so its scrolling parent cannot clip it.
            self.browser.evaluate('document.querySelector(' + json.dumps(tabs) + ').querySelector("button").focus()')
            self.key('Tab', 9)
            self.key('Tab', 9, modifiers=8)
            focus = self.browser.evaluate("""((selector)=>{
              const e=document.activeElement,s=getComputedStyle(e);
              return {tab:document.querySelector(selector).contains(e),visible:e.matches(':focus-visible'),style:s.outlineStyle,width:s.outlineWidth,offset:s.outlineOffset};
            })(""" + json.dumps(tabs) + ')')
            self.assertEqual(focus, {'tab': True, 'visible': True, 'style': 'solid',
                                     'width': '2px', 'offset': '-2px'}, label)
            shared[label]['keyboardFocus'] = focus

        self.viewport(1366)
        row = '[data-author-action=open][data-id="' + workflow_id + '"]'
        self.wait('document.querySelector(' + json.dumps(row) + ')')
        self.click(row)
        self.wait("document.querySelector('.ew-author-tabs [aria-selected=true]')")
        original = deepcopy(self.state(workflow_id=workflow_id)['workflow']['draft'])
        capture_style('author-content', '.ew-author-tabs')
        capture_tab_focus('author-content', '.ew-author-tabs')
        self.screenshot('shared-panel-authoring-1366')
        self.open_author_job_ui('job-0')
        capture_style('author-job', '.ew-author-tabs')
        for tab in ('rules', 'history'):
            self.click('[data-author-action=tab][data-tab=' + tab + ']')
            self.wait("document.querySelector('.ew-author-tabs [data-tab=" + tab + "]')?.getAttribute('aria-selected') === 'true'")
            capture_style('author-' + tab, '.ew-author-tabs')
        hover('.ew-author-tabs [aria-selected=false]', 'rgb(236, 236, 239)')
        self.open_workspace_assets()
        self.click('[data-action=tools]')
        self.wait("document.querySelector('#ees-work-designer[data-author-tab=tools]')")
        capture_style('tools')
        run = self.start(workflow_id)
        self.open_sidebar()
        self.click('[data-action=mode][data-mode=work]')
        self.wait("document.querySelector('[data-action=records]')")
        self.open_run(workflow_id, run, job=None)
        if not self.browser.evaluate("!!document.querySelector('.ew-operation-overview')"):
            self.click('[data-action=stage_back]')
        self.wait("document.querySelector('.ew-operation-overview')")
        capture_style('work-overview')
        self.click('.ew-operation-stage[data-action=stage_open]')
        self.wait("document.querySelector('#ees-work-panel.ew-vd .ew-tabs')")
        capture_style('work-stage', '.ew-tabs')
        capture_tab_focus('work-stage', '.ew-tabs')
        self.screenshot('shared-panel-stage-1366')
        hover('.ew-tabs [aria-pressed=false]', 'rgb(236, 236, 239)')
        self.open_run(workflow_id, run)
        self.wait("document.querySelector('#ees-work-panel:not(.ew-vd) .ew-tabs')")
        capture_style('work-task', '.ew-tabs')
        # open_run explicitly expands the sidebar. Both 1366 and 480 are
        # below the auto-collapse breakpoint, so resizing preserves that
        # manual choice. Prepare the compact layout through its real control.
        self.click('[data-ees-sidebar-toggle]')
        self.wait("document.querySelector('[data-ees-source-sidebar]')?.dataset.compact === 'true'")
        self.viewport(480, overlay=True)
        capture_style('work-task-narrow', '.ew-tabs')
        capture_tab_focus('work-task-narrow', '.ew-tabs')
        self.assertEqual(self.state(workflow_id=workflow_id)['workflow']['draft'], original)
        directory = self.screenshot('shared-panel-task-480')
        (directory / 'shared-panel-styles.json').write_text(
            json.dumps(shared, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

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
