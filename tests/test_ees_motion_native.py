"""C3 motion in the actual packaged Svelte frontend, with trusted CDP input.

Native account/chat responses and external transports are synthetic; the built
frontend and temporary workflow service are real. Frame/style observations are
retained alongside screenshots so still images cannot count as motion evidence.
"""
import json
import os
from pathlib import Path
import threading
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from ees_work_integrated_fixture import IntegratedNativeCase
from native_ui_fixture import NativeUIHandler


class MotionNativeTests(IntegratedNativeCase):
    def capture_failure(self):
        super().capture_failure()
        if (not getattr(self, 'failure_evidence_captured', False)
                or getattr(self, 'motion_failure_captured', False)
                or not self.browser.session):
            return
        self.motion_failure_captured = True
        evidence = self.browser.evaluate('window.__c3?.evidence || null')
        directory = Path(os.environ.get('EES_TEST_SCREENSHOT_DIR',
                         Path(__file__).resolve().parents[1] / 'dist/ees-work-screenshots'))
        directory.mkdir(parents=True, exist_ok=True)
        (directory / (self._testMethodName + '-failure-frames.json')).write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def viewport(self, width, height):
        self.browser.call('Emulation.setDeviceMetricsOverride', {
            'width': width, 'height': height, 'deviceScaleFactor': 1, 'mobile': False})
        self.wait('innerWidth === ' + str(width) + ' && innerHeight === ' + str(height))
        self.wait("document.querySelector('.ees-panel-region')?.dataset.overlay === " +
                  json.dumps('true' if width < 1096 else 'false'))

    def observe(self, label):
        self.browser.evaluate("""(()=>{
          window.__c3?.stop();
          const evidence={label:""" + json.dumps(label) + """,frames:[],events:[],inputs:[]};
          let active=true;
          const identify=element=>({tag:element?.tagName||'',id:element?.id||'',
            action:element?.dataset?.action||element?.dataset?.authorAction||''});
          const snapshot=element=>{const s=getComputedStyle(element),r=element.getBoundingClientRect();
            return {kind:element.dataset.eesMotionKind,state:element.dataset.eesMotion||'',
              id:element.id,opacity:Number(s.opacity),transform:s.transform,width:r.width,
              duration:s.animationDuration,easing:s.animationTimingFunction,name:s.animationName,
              transitionProperty:s.transitionProperty,inert:element.inert,hidden:element.hidden,
              ariaHidden:element.getAttribute('aria-hidden'),pointerEvents:s.pointerEvents,
              modal:element.matches(':modal')};};
          const sample=()=>{if(!active)return;const nodes=[...document.querySelectorAll('[data-ees-motion-kind]')];
            evidence.frames.push({t:performance.now(),nodes:nodes.map(snapshot),
              focus:identify(document.activeElement),
              system:document.querySelector('#ees-work-system-trigger')?.textContent||'',
              scopeCount:document.querySelectorAll('[data-scope-dropdown]').length,
              dialogCount:document.querySelectorAll('#ees-work-dialog').length,
              chatWidth:document.querySelector('.ees-chat-region')?.getBoundingClientRect().width,
              panelWidth:document.querySelector('.ees-panel-region')?.getBoundingClientRect().width});
            requestAnimationFrame(sample);};
          const animation=event=>{if(event.target.matches('[data-ees-motion-kind]'))
            evidence.events.push({t:performance.now(),type:event.type,...snapshot(event.target)});};
          const input=event=>{const row={type:event.type,key:event.key||'',trusted:event.isTrusted,
            t:performance.now(),opening:!!document.querySelector('[data-ees-motion=opening]'),
            closing:!!document.querySelector('[data-ees-motion=closing]'),
            overlayOpen:!!document.querySelector('.ees-panel-region[data-overlay=true]:not([hidden])'),
            composer:!!event.target.closest?.('#chat-input'),target:identify(event.target),
            scopeChoice:event.target.closest?.('[data-action=choose_system]')?.dataset.systemId||'',
            defaultPreventedAtCapture:event.defaultPrevented,eventPhaseAtCapture:event.eventPhase};
            evidence.inputs.push(row);queueMicrotask(()=>{row.defaultPreventedAfter=event.defaultPrevented;
              row.focusAfter=identify(document.activeElement);});};
          for(const name of ['animationstart','animationend','animationcancel'])document.addEventListener(name,animation,true);
          for(const name of ['keydown','pointerdown'])document.addEventListener(name,input,true);
          const mutations=new MutationObserver(records=>{for(const record of records){
            const e=record.target;if(e.matches?.('[data-ees-motion-kind]')&&e.isConnected)
              evidence.events.push({t:performance.now(),type:'state',...snapshot(e)});}});
          mutations.observe(document,{subtree:true,attributes:true,attributeFilter:['data-ees-motion','inert']});
          window.__c3={evidence,stop:()=>{active=false;mutations.disconnect();
            for(const name of ['animationstart','animationend','animationcancel'])document.removeEventListener(name,animation,true);
            for(const name of ['keydown','pointerdown'])document.removeEventListener(name,input,true);}};
          requestAnimationFrame(sample);
        })()""")

    def finish_evidence(self, label):
        evidence = self.browser.evaluate('(()=>{window.__c3.stop();return window.__c3.evidence;})()')
        directory = self.screenshot(label)
        (directory / (label + '-frames.json')).write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        self.assertTrue(evidence['frames'], 'No rendered animation frames observed')
        self.assertTrue(evidence['inputs'], 'No trusted browser input observed')
        self.assertTrue(all(event['trusted'] for event in evidence['inputs']))
        self.assertTrue(all(row['scopeCount'] <= 1 and row['dialogCount'] <= 1 for row in evidence['frames']))
        return evidence

    def assert_effect(self, evidence, kind, state, *, reduced=False):
        rows = [row for row in evidence['events'] if row['kind'] == kind and row['state'] == state]
        if reduced:
            self.assertFalse([row for row in rows if row['duration'] not in ('0s', '0ms')], rows)
            return
        self.assertTrue(rows, 'No observed ' + kind + ' ' + state + ' style')
        duration = '0.2s' if state == 'opening' else '0.15s'
        easing = 'cubic-bezier(0.2, 0.8, 0.2, 1)' if state == 'opening' else 'cubic-bezier(0.4, 0, 1, 1)'
        self.assertTrue(any(row['duration'] == duration and row['easing'] == easing for row in rows), rows)
        frames = [node for frame in evidence['frames'] for node in frame['nodes']
                  if node['kind'] == kind and node['state'] == state]
        self.assertTrue(any(0 < node['opacity'] < 1 for node in frames),
                        'No rendered intermediate opacity for ' + kind + ' ' + state)
        if state == 'closing':
            self.assertTrue(all(row['inert'] and row['pointerEvents'] == 'none' for row in rows), rows)

    def activate(self, key='Enter'):
        code, number, text = ('Enter', 13, '\r') if key == 'Enter' else ('Space', 32, ' ')
        self.browser.call('Input.dispatchKeyEvent', {'type': 'keyDown', 'key': key, 'code': code,
            'windowsVirtualKeyCode': number, 'nativeVirtualKeyCode': number,
            'text': text, 'unmodifiedText': text})
        self.browser.call('Input.dispatchKeyEvent', {'type': 'keyUp', 'key': key, 'code': code,
            'windowsVirtualKeyCode': number, 'nativeVirtualKeyCode': number})

    def click_now(self, selector):
        """Trusted input at the current visible point, during an opening tween."""
        point = self.browser.evaluate('(()=>{const e=document.querySelector(' + json.dumps(selector) +
            '),r=e.getBoundingClientRect(),x=r.x+r.width/2,y=r.y+r.height/2;'
            'return e.contains(document.elementFromPoint(x,y))?{x,y}:null;})()')
        self.assertIsNotNone(point, 'Animated control is not hit-testable: ' + selector)
        for kind in ('mousePressed', 'mouseReleased'):
            self.browser.call('Input.dispatchMouseEvent', {'type': kind, **point, 'button': 'left',
                'buttons': int(kind == 'mousePressed'), 'clickCount': 1})

    def test_c3_attached_panel_fades_content_without_width_tween_and_preserves_work(self):
        identifier = self.author(fields=[{'id': 'note', 'type': 'text', 'scope': 'run'}] +
            [{'id': 'field-' + str(index), 'type': 'text'} for index in range(20)], jobs=1)
        run = self.start(identifier)
        self.open_run(identifier, run)
        self.fill('[data-work-input][name=note]', '전환해도 보존할 미저장 입력')
        self.fill('#chat-input', '전환해도 보존할 대화 초안')
        draft = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        settings = self.browser.evaluate("window.__eesMotionV1.settings(document.querySelector('#ees-work-panel'))")
        self.assertEqual({key: settings[key] for key in ('fast', 'open', 'close')},
                         {'fast': 120, 'open': 200, 'close': 150})
        for width, height in ((1366, 768), (1920, 1080)):
            self.viewport(width, height)
            self.observe('attached-' + str(width))
            self.click('#ees-work-panel [data-action=close_panel]')
            self.wait("document.querySelector('.ees-panel-region').hidden")
            self.wait("document.activeElement?.matches('[data-action=open_panel]')")
            self.activate()
            self.wait("!document.querySelector('.ees-panel-region').hidden")
            self.wait("!document.querySelector('[data-ees-motion=opening]')")
            evidence = self.finish_evidence('c3-attached-' + str(width) + 'x' + str(height))
            self.assert_effect(evidence, 'panel-content', 'opening')
            widths = {round(row['panelWidth'], 3) for row in evidence['frames']}
            self.assertTrue(widths <= {0, 480}, widths)
            self.assertFalse([row for row in evidence['events'] if row['kind'] == 'panel-overlay'
                              and row['state'] in ('opening', 'closing')])
            self.assertEqual(self.read('[data-work-input][name=note]', 'value'), '전환해도 보존할 미저장 입력')
            self.assertEqual(self.browser.evaluate('window.__eesNativeDraftV1.read()'), draft)
            self.assertIn('기존 대화 기록', self.text('body'))
        # Actual pointer movement must resize before pointer-up, without waiting
        # for the 120/200ms motion durations.
        point = self.browser.evaluate("(()=>{const r=document.querySelector('[data-ees-panel-resize]').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+80};})()")
        self.browser.call('Input.dispatchMouseEvent', {'type': 'mousePressed', **point, 'button': 'left', 'buttons': 1, 'clickCount': 1})
        self.browser.call('Input.dispatchMouseEvent', {'type': 'mouseMoved', 'x': point['x'] - 80,
            'y': point['y'], 'button': 'left', 'buttons': 1})
        self.assertEqual(self.read('.ees-panel-region', 'getBoundingClientRect().width'), 560)
        self.browser.call('Input.dispatchMouseEvent', {'type': 'mouseReleased', 'x': point['x'] - 80,
            'y': point['y'], 'button': 'left', 'buttons': 0, 'clickCount': 1})
        self.assertEqual(self.state(run_id=run['id'])['run']['inputs'], {})
        self.assertEqual(self.server.completions, [])

    def test_c3_scope_immediate_escape_reopen_replacement_and_reduced_motion(self):
        trigger = '#ees-work-system-trigger'
        # Production workspace responses filter factories by system. Exercise
        # both the asynchronous APC response and cached EMS catalog replacement.
        self.command('save_factory', factory_id='c3-ems-factory',
                     system_id='EMS', name='C3 시스템별 공장')
        self.assertIsNotNone(self.refresh())
        self.observe('scope-rapid')
        self.click(trigger)
        self.wait("document.querySelector('[data-scope-dropdown=system]')")
        self.key('Escape', 27)
        # The trigger remains an actual clickable target during exit.
        self.click(trigger)
        self.wait("document.querySelector('[data-scope-dropdown=system]') && document.querySelector('#ees-work-system-trigger').ariaExpanded === 'true'")
        self.wait("!document.querySelector('[data-ees-motion=opening]')")
        self.click('#ees-work-site-trigger')
        self.wait("document.querySelector('[data-scope-dropdown=factory]') && document.querySelectorAll('[data-scope-dropdown]').length===1")
        # The first system Escape intentionally interrupts entry. Also close a
        # fully entered surface so intermediate exit opacity is observable.
        self.wait("!document.querySelector('[data-ees-motion=opening]')")
        self.key('Escape', 27)
        self.wait("!document.querySelector('[data-scope-dropdown]')")
        self.wait("document.activeElement?.id === 'ees-work-site-trigger'")
        evidence = self.finish_evidence('c3-scope-rapid-reopen')
        self.assert_effect(evidence, 'scope', 'opening')
        self.assert_effect(evidence, 'scope', 'closing')
        self.assertTrue(any(row['key'] == 'Escape' and row['opening'] for row in evidence['inputs']),
                        'Escape was not actually delivered during opening')
        # An explicit choice updates scope immediately, but its own retained
        # menu still completes the shared close before returning focus.
        for target in ('APC', 'EMS'):
            self.observe('scope-selection-' + target)
            self.click(trigger)
            self.wait("document.querySelector('[data-scope-dropdown=system]') && !document.querySelector('[data-ees-motion=opening]')")
            self.click('[data-action=choose_system][data-system-id=' + target + ']')
            self.wait("!document.querySelector('[data-scope-dropdown]') && document.activeElement?.id==='ees-work-system-trigger'")
            self.assertIn(target, self.text(trigger))
            evidence = self.finish_evidence('c3-scope-selection-close-focus-' + target.lower())
            self.assertTrue(any(row['trusted'] and row['scopeChoice'] == target for row in evidence['inputs']))
            self.assert_effect(evidence, 'scope', 'closing')
            closing_frames = [frame for frame in evidence['frames'] if any(
                node['kind'] == 'scope' and node['state'] == 'closing' for node in frame['nodes'])]
            self.assertTrue(all(target in frame['system'] for frame in closing_frames),
                            'Selected scope was delayed until its close effect finished')
            self.assertTrue(all(frame['focus']['id'] != 'ees-work-system-trigger' for frame in closing_frames),
                            'Selected scope returned focus before its close effect finished')
            self.assertIsNotNone(self.refresh())
        self.browser.call('Emulation.setEmulatedMedia', {'features': [{'name': 'prefers-reduced-motion', 'value': 'reduce'}]})
        self.addCleanup(lambda: self.browser.call('Emulation.setEmulatedMedia', {'features': []}))
        self.observe('scope-reduced')
        self.click(trigger)
        self.wait("document.querySelector('[data-scope-dropdown=system]')")
        computed = self.browser.evaluate("(()=>{const e=document.querySelector('[data-scope-dropdown]'),s=getComputedStyle(e);return {settings:window.__eesMotionV1.settings(e),duration:s.animationDuration};})()")
        self.assertEqual([computed['settings'][key] for key in ('fast', 'open', 'close')], [0, 0, 0])
        self.assertEqual(computed['duration'], '0s')
        self.key('Escape', 27)
        self.wait("!document.querySelector('[data-scope-dropdown]') && document.activeElement?.id==='ees-work-system-trigger'")
        evidence = self.finish_evidence('c3-scope-reduced-motion')
        self.assert_effect(evidence, 'scope', 'opening', reduced=True)
        self.assert_effect(evidence, 'scope', 'closing', reduced=True)

    def test_c3_overlay_panel_closing_releases_hit_testing_and_restores_focus(self):
        self.viewport(1095, 768)
        self.observe('overlay-rapid')
        self.click('#ees-work-panel [data-action=close_panel]')
        self.wait("document.querySelector('.ees-panel-region').hidden")
        self.wait("document.activeElement?.matches('[data-action=open_panel]')")
        self.activate()
        self.wait("!document.querySelector('.ees-panel-region').hidden")
        # Reopen during the existing close button's exit, then exercise the C3
        # overlay Escape path separately with no nested dialog/menu present.
        self.click_now('#ees-work-panel [data-action=close_panel]')
        self.click('[data-action=open_panel]')
        self.wait("!document.querySelector('.ees-panel-region').hidden && !document.querySelector('[data-ees-motion=opening]')")
        # C54: the visible conversation remains usable while the overlapping
        # panel is fully open, not only after its close has released a blocker.
        self.click_now('#chat-input')
        self.assertTrue(self.browser.evaluate("document.activeElement === document.querySelector('#chat-input')"))
        self.browser.call('Input.insertText', {'text': '겹친 패널이 열린 동안 입력한 대화 초안'})
        self.assertIn('겹친 패널이 열린 동안 입력한 대화 초안', self.text('#chat-input'))
        self.assertFalse(self.read('.ees-panel-region', 'hidden'))
        draft = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        # C60: observe the actual target and document bubbling, independently of
        # capture/defaultPrevented (Native CLOSE_MODAL legitimately prevents it).
        self.browser.evaluate("""(()=>{
          const composer=document.querySelector('#chat-input');
          const panel=document.querySelector('.ees-panel-region');
          const deliveries=window.__c3.evidence.escapeDeliveries=[];
          const ids=new WeakMap();let nextId=0;
          const record=location=>event=>{if(event.key!=='Escape')return;
            if(!ids.has(event))ids.set(event,++nextId);
            deliveries.push({id:ids.get(event),location,phase:event.eventPhase,
              trusted:event.isTrusted,t:performance.now(),
              composer:composer.contains(event.target),panel:panel.contains(event.target),
              overlayOpen:panel.dataset.overlay==='true'&&!panel.hidden,
              opening:panel.dataset.eesMotion==='opening',closing:panel.dataset.eesMotion==='closing'});};
          const targets=[[composer,record('composer')],[panel,record('panel')],
            [document,record('document')]];
          for(const [target,listener]of targets)target.addEventListener('keydown',listener);
          const stop=window.__c3.stop;
          window.__c3.stop=()=>{for(const [target,listener]of targets)
            target.removeEventListener('keydown',listener);stop();};
        })()""")
        self.key('Escape', 27)
        composer_escape = self.browser.evaluate("""new Promise(resolve=>{
          const panel=document.querySelector('.ees-panel-region');
          const close=window.__eesMotionV1.settings(panel).close;
          setTimeout(()=>{const result={t:performance.now(),close,
            hidden:panel.hidden,closing:panel.dataset.eesMotion==='closing',
            focus:document.activeElement?.id,
            draft:window.__eesNativeDraftV1.read(),
            deliveries:window.__c3.evidence.escapeDeliveries.slice()};
            window.__c3.evidence.composerEscapeAfter=result;resolve(result);},close+100);
        })""")
        self.assertFalse(composer_escape['hidden'], composer_escape)
        self.assertFalse(composer_escape['closing'], composer_escape)
        self.assertEqual(composer_escape['focus'], 'chat-input')
        self.assertEqual(composer_escape['draft'], draft)
        composer_deliveries = composer_escape['deliveries']
        self.assertEqual([row['location'] for row in composer_deliveries], ['composer', 'document'])
        self.assertEqual(len({row['id'] for row in composer_deliveries}), 1)
        self.assertTrue(all(row['trusted'] and row['composer'] and row['overlayOpen']
                            and not row['opening'] and not row['closing'] for row in composer_deliveries))
        self.assertEqual(composer_deliveries[-1]['phase'], 3, 'Escape did not reach document bubbling')
        self.assertGreater(composer_escape['t'] - composer_deliveries[0]['t'], composer_escape['close'])
        self.click('#ees-work-panel [data-action=close_panel]')
        self.wait("document.querySelector('.ees-panel-region').hidden")
        self.wait("document.activeElement?.matches('[data-action=open_panel]')")
        self.activate(' ')
        self.wait("!document.querySelector('.ees-panel-region').hidden && !document.querySelector('[data-ees-motion=opening]')")
        self.key('Escape', 27)
        self.wait("document.querySelector('.ees-panel-region').hidden")
        self.wait("document.activeElement?.matches('[data-action=open_panel]')")
        panel_deliveries = self.browser.evaluate('window.__c3.evidence.escapeDeliveries.slice(' +
                                                  str(len(composer_deliveries)) + ')')
        self.assertEqual([row['location'] for row in panel_deliveries], ['panel'],
                         'Panel Escape reached document bubbling')
        self.assertTrue(panel_deliveries[0]['trusted'] and panel_deliveries[0]['panel']
                        and panel_deliveries[0]['overlayOpen'], panel_deliveries)
        self.activate()
        self.wait("!document.querySelector('.ees-panel-region').hidden && !document.querySelector('[data-ees-motion=opening]')")
        self.click('#ees-work-system-trigger')
        self.wait("document.querySelector('[data-scope-dropdown=system]')")
        self.key('Escape', 27)
        self.wait("!document.querySelector('[data-scope-dropdown]')")
        self.assertFalse(self.read('.ees-panel-region', 'hidden'), 'Menu Escape also closed its underlying panel')
        # Exit releases hit testing immediately. A real new focus choice must
        # survive completion instead of the old close task stealing it back.
        self.click('#ees-work-panel [data-action=close_panel]')
        self.click_now('#chat-input')
        self.wait("document.querySelector('.ees-panel-region').hidden")
        self.assertTrue(self.browser.evaluate("document.activeElement === document.querySelector('#chat-input')"))
        evidence = self.finish_evidence('c3-overlay-close-reopen')
        self.assert_effect(evidence, 'panel-overlay', 'opening')
        self.assert_effect(evidence, 'panel-overlay', 'closing')
        self.assertTrue(any(row['composer'] and row['overlayOpen']
                            and not row['opening'] and not row['closing'] for row in evidence['inputs']),
                        'The visible composer was not actually clicked while the overlay panel was open')
        self.assertTrue(any(row['composer'] and row['closing'] for row in evidence['inputs']),
                        'The composer was not actually clicked during panel exit')
        self.assertEqual(self.browser.evaluate('window.__eesNativeDraftV1.read()'), draft)
        self.assertTrue(all(abs(row['chatWidth'] - 1039) < .02 for row in evidence['frames']),
                        'Overlay animation changed the conversation layout')

    def test_c3_dialog_and_help_close_preserve_draft_and_release_modal_blocker(self):
        name = '모달 움직임 검증 절차'
        identifier = self.command('create_workflow', name=name, system_id='EMS')['workflow_id']
        stored = self.state(workflow_id=identifier)['workflow']
        self.refresh()
        self.fill('#chat-input', '확인 창과 도움말 왕복 후 보존할 문장')
        draft = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        self.click('[data-action=mode][data-mode=author]')
        self.click('[data-author-action=open][data-id="' + identifier + '"]')
        self.wait("document.querySelector('.ew-procedure-menu > summary')")

        def open_copy_dialog():
            # The workflow menu is revealed by trusted hover/focus in HTML 12.
            if not self.read('.ew-procedure-menu', 'open'):
                point = self.browser.evaluate("(()=>{const r=document.querySelector('.ew-procedure-menu > summary').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()")
                self.browser.call('Input.dispatchMouseEvent', {'type': 'mouseMoved', **point})
                self.click('.ew-procedure-menu > summary')
            self.click('[data-author-action=copy]')
            self.wait("document.querySelector('#ees-work-dialog')?.open")

        self.observe('dialog-help')
        # New workflows are inline. The existing copy dialog still exercises
        # the actual modal blocker in attached mode and inside an overlay panel.
        self.viewport(1920, 1080)
        open_copy_dialog()
        self.key('Escape', 27)
        self.click_now('#chat-input')
        self.wait("!document.querySelector('#ees-work-dialog')")
        self.assertTrue(self.browser.evaluate("document.activeElement === document.querySelector('#chat-input')"))
        self.viewport(1000, 768)
        open_copy_dialog()
        self.key('Escape', 27)
        self.wait("!document.querySelector('#ees-work-dialog')")
        self.assertFalse(self.read('.ees-panel-region', 'hidden'), 'Dialog Escape also closed its underlying panel')
        self.wait("document.activeElement?.matches('[data-author-action=copy]')")
        self.activate()
        self.wait("document.querySelector('#ees-work-dialog [name=name]')")
        copy_name = self.read('#ees-work-dialog [name=name]', 'value')
        self.fill('#ees-work-dialog [name=name]', '취소할 복사 이름')
        self.click('[data-dialog-cancel]')
        self.wait("!document.querySelector('#ees-work-dialog')")
        open_copy_dialog()
        self.assertEqual(self.read('#ees-work-dialog [name=name]', 'value'), copy_name)
        self.key('Escape', 27)
        self.wait("!document.querySelector('#ees-work-dialog')")
        self.assertEqual(self.state(workflow_id=identifier)['workflow'], stored)
        # Keep the original creation-buffer assertion on its current inline UI.
        self.click('[data-author-action=list]')
        self.click('[data-author-action=create]')
        self.wait("document.querySelector('#ew-procedure-create #ew-procedure-name')")
        self.fill('#ew-procedure-name', '다시 열어도 남는 이름')
        self.click('[data-author-action=procedure_cancel]')
        self.wait("!document.querySelector('#ew-procedure-create')")
        self.wait("document.activeElement?.matches('[data-author-action=create]')")
        self.activate()
        self.wait("document.querySelector('#ew-procedure-create #ew-procedure-name')")
        self.assertEqual(self.read('#ew-procedure-name', 'value'), '다시 열어도 남는 이름')
        self.key('Escape', 27)
        self.wait("!document.querySelector('#ew-procedure-create')")
        self.assertFalse(self.read('.ees-panel-region', 'hidden'), 'Inline Escape also closed its underlying panel')
        self.click('[data-action=tools]')
        self.click('[data-author-action=tool_create]')
        self.click('[data-author-action=tool_example][data-id=jira-query]')
        self.click('[data-author-action=help][data-id=read_tool]')
        self.wait("document.querySelector('#ees-work-help')")
        self.wait("!document.querySelector('#ees-work-help[data-ees-motion=opening]')")
        self.key('Escape', 27)
        self.wait("!document.querySelector('#ees-work-help')")
        self.assertFalse(self.read('.ees-panel-region', 'hidden'), 'Help Escape also closed its underlying panel')
        self.wait("document.activeElement?.matches('[data-author-action=help][data-id=read_tool]')")
        evidence = self.finish_evidence('c3-dialog-help-focus')
        self.assertTrue(any(row['composer'] and row['closing'] for row in evidence['inputs']),
                        'The composer was not actually clicked during dialog exit')
        for kind in ('dialog', 'help'):
            self.assert_effect(evidence, kind, 'opening')
            self.assert_effect(evidence, kind, 'closing')
        closing = [row for row in evidence['events'] if row['kind'] == 'dialog' and row['state'] == 'closing']
        self.assertTrue(all(not row['modal'] for row in closing), closing)
        self.assertEqual(self.browser.evaluate('window.__eesNativeDraftV1.read()'), draft)
        self.assertEqual(self.server.completions, [])

    def test_c3_scope_slow_failure_and_out_of_order_responses_do_not_restore_stale_scope(self):
        self.fill('#chat-input', '느린 응답 중 보존할 문장')
        draft = self.browser.evaluate('window.__eesNativeDraftV1.read()')
        release, started, finished, ems_finished = (threading.Event() for _ in range(4))
        self.addCleanup(release.set)
        original = NativeUIHandler.do_GET
        server = self.server
        deliveries = []

        def transport(handler):
            url = urlsplit(handler.path)
            system = parse_qs(url.query).get('system_id', [''])[0]
            if handler.server is not server or url.path != '/api/ees-work/workspace':
                return original(handler)
            if system == 'APC':
                started.set()
                release.wait(timeout=8)
                try:
                    return original(handler)
                finally:
                    deliveries.append('APC')
                    finished.set()
            if system == 'FDC':
                deliveries.append('FDC-error')
                return handler.send_workflow({'ok': False, 'error': {
                    'code': 'workspace_unavailable', 'message': '합성 범위 조회 실패'}})
            try:
                return original(handler)
            finally:
                deliveries.append(system)
                if system == 'EMS':
                    ems_finished.set()

        with patch.object(NativeUIHandler, 'do_GET', transport):
            self.observe('scope-response-order')
            self.click('#ees-work-system-trigger')
            self.click('[data-action=choose_system][data-system-id=APC]')
            self.assertTrue(started.wait(timeout=2))
            self.assertIn('APC', self.text('#ees-work-system-trigger'))
            self.assertIn('받는 중', self.text('#ees-work-entry'))
            self.assertEqual(self.browser.evaluate('window.__eesNativeDraftV1.read()'), draft)
            self.click('#ees-work-system-trigger')
            self.click('[data-action=choose_system][data-system-id=EMS]')
            self.wait("document.querySelector('#ees-work-system-trigger')?.textContent.includes('EMS') && !document.querySelector('[data-ees-scope-loading]')")
            self.assertTrue(ems_finished.wait(timeout=3))
            release.set()
            self.assertTrue(finished.wait(timeout=3))
            self.browser.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
            self.assertIn('EMS', self.text('#ees-work-system-trigger'))
            self.assertLess(deliveries.index('EMS'), deliveries.index('APC'))
            self.click('#ees-work-system-trigger')
            self.click('[data-action=choose_system][data-system-id=FDC]')
            self.wait("document.querySelector('#ees-work-panel')?.textContent.includes('합성 범위 조회 실패')")
            self.assertIn('FDC', self.text('#ees-work-system-trigger'))
            self.assertEqual(self.browser.evaluate('window.__eesNativeDraftV1.read()'), draft)
            self.click('#ees-work-system-trigger')
            self.click('[data-action=choose_system][data-system-id=EMS]')
            self.wait("document.querySelector('#ees-work-system-trigger')?.textContent.includes('EMS') && !document.querySelector('#ees-work-panel')?.textContent.includes('합성 범위 조회 실패')")
            evidence = self.finish_evidence('c3-scope-response-order')
            evidence['delivery_order'] = deliveries
            directory = self.screenshot('c3-scope-response-order-final')
            (directory / 'c3-scope-response-order-deliveries.json').write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        self.assertEqual(self.browser.evaluate('window.__eesNativeDraftV1.read()'), draft)
        self.assertEqual(self.server.completions, [])
