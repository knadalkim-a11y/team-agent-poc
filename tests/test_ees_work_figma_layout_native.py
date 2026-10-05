"""Q1 actual built Native geometry and private panel preferences.

Native frontend, assets and workspace SQLite are real. Sessions and source data
are synthetic here; the complete app/account gates test actual Native login.
"""
from copy import deepcopy
import json
import time

from ees_work_integrated_fixture import IntegratedNativeCase


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
        self.wait('document.body.dataset.eesSidebarCompact === ' + json.dumps(str(width < 1440).lower()))
        self.wait("Math.abs(document.querySelector('#chat-container').getBoundingClientRect().width - "+str(width-(56 if width<1440 else 256))+") < .01")

    def geometry(self):
        return self.browser.evaluate("""(()=>{
          const box=s=>{const e=document.querySelector(s),r=e?.getBoundingClientRect();return r?{x:r.x,y:r.y,width:r.width,height:r.height,bottom:r.bottom}:null;};
          return {viewport:[innerWidth,innerHeight],sidebar:box('#sidebar'),panel:box('#ees-work-panel'),chat:box('.ees-integrated-chat'),message:box('.message-listitem'),composer:box('#message-input-container'),footer:box('#ees-work-panel>.ew-job-actions'),overflow:document.documentElement.scrollWidth>innerWidth,overlay:document.querySelector('#ees-work-panel').dataset.eesOverlay};
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
        self.assertEqual(self.geometry()['panel']['width'],720)
        self.assertEqual(self.geometry()['chat']['width'],504)
        self.assertEqual(self.geometry()['overlay'],'false')
        self.resize_keyboard('Home',36)
        self.assertEqual(self.geometry()['panel']['width'],400)
        self.viewport(1095)
        self.assertEqual(self.geometry()['overlay'],'true')
        self.assertEqual(self.geometry()['chat']['width'],1039)
        self.click('[data-action=close_panel]')
        self.wait("document.querySelector('#ees-work-panel').hidden")
        self.click('[data-action=open_panel]')
        self.wait("!document.querySelector('#ees-work-panel').hidden")
        self.evidence('q1-overlay-close-reopen')

    def test_q1_physical_drag_restores_per_actor_width_and_contrast(self):
        handle=self.browser.evaluate("(()=>{const r=document.querySelector('[data-ees-panel-resize]').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+100};})()")
        self.browser.call('Input.dispatchMouseEvent',{'type':'mousePressed',**handle,'button':'left','buttons':1,'clickCount':1})
        self.browser.call('Input.dispatchMouseEvent',{'type':'mouseMoved','x':handle['x']-160,'y':handle['y'],'button':'left','buttons':1})
        self.browser.call('Input.dispatchMouseEvent',{'type':'mouseReleased','x':handle['x']-160,'y':handle['y'],'button':'left','buttons':0,'clickCount':1})
        self.wait("document.querySelector('#ees-work-panel').getBoundingClientRect().width === 640")
        self.wait_saved_width(640)
        actor_a=dict(self.server.user)
        self.navigate('/c/existing-chat');self.wait("document.querySelector('#ees-work-panel')?.getBoundingClientRect().width===640")
        self.users['other-user']={**deepcopy(actor_a),'id':'other-user','name':'Other synthetic user'}
        self.server.user=self.users['other-user']
        self.navigate('/');self.wait("document.querySelector('#ees-work-panel')?.getBoundingClientRect().width===480")
        self.resize_keyboard('Home',36)
        self.wait_saved_width(400)
        self.server.user=actor_a
        self.navigate('/c/existing-chat');self.wait("document.querySelector('#ees-work-panel')?.getBoundingClientRect().width===640")
        ratios=self.browser.evaluate("""(()=>{
          const style=getComputedStyle(document.querySelector('#ees-work-panel')),hex=n=>style.getPropertyValue(n).trim();
          const lum=h=>{const c=h.replace('#','').match(/../g).map(x=>parseInt(x,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return c[0]*.2126+c[1]*.7152+c[2]*.0722;};
          const ratio=(a,b)=>(Math.max(lum(a),lum(b))+.05)/(Math.min(lum(a),lum(b))+.05);
          return {amber:hex('--ees-status-attention'),green:hex('--ees-status-success'),attention:ratio(hex('--ees-status-attention'),hex('--ees-status-attention-bg')),success:ratio(hex('--ees-status-success'),hex('--ees-status-success-bg')),danger:ratio(hex('--ees-status-danger'),hex('--ees-status-danger-bg')),body:ratio(hex('--ees-text-primary'),'#ffffff'),secondary:ratio(hex('--ees-text-secondary'),'#ffffff'),meta:ratio(hex('--ees-text-tertiary'),'#fafafa')};
        })()""")
        self.assertEqual(ratios['amber'],'#96590c');self.assertEqual(ratios['green'],'#2a744c')
        for name in ('attention','success','danger','body','secondary','meta'):self.assertGreaterEqual(ratios[name],4.5,name)
        directory=self.screenshot('q1-private-width-640')
        (directory/'q1-contrast.json').write_text(json.dumps(ratios,indent=2)+'\n',encoding='utf-8')
