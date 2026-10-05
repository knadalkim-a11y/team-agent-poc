"""Actual integrated runtime/UI with a synthetic read-only transport boundary."""
import asyncio
import json
from uuid import uuid4
from ees_work_integrated_fixture import IntegratedNativeCase


class CPhaseTwoNativeTests(IntegratedNativeCase):
    def tool(self, required=False):
        key=self.author(mode='tool',fields=[{'id':'target','name':'조회 대상','type':'text','scope':'run','required':required}])
        run=self.start(key,inputs={} if required else {'target':'합성 대상'})
        self.open_run(key,run)
        return key,run

    def test_real_tool_call_snapshots_inputs_but_does_not_confirm_business_completion(self):
        key,run=self.tool();self.click('[data-action="execute"]')
        self.assertTrue(self.bridge.started.wait(3))
        self.wait("document.querySelector('#ees-work-panel .ew-status[data-status=waiting_confirmation]')")
        saved=self.state(run_id=run['id'])['run']
        self.assertEqual(len(self.bridge.calls),1);self.assertEqual(self.bridge.calls[0]['arguments'],{'target':'합성 대상'})
        self.assertEqual(saved['attempts'][0]['inputs'],{'target':'합성 대상'})
        self.assertNotEqual(saved['jobs']['job-0']['status'],'completed')
        self.assertEqual(saved['jobs']['job-0']['decisions'],[])
        self.click('[data-action="tab"][data-tab="history"]');self.click('.ew-history summary')
        self.assertIn('합성 대상',self.text('#ees-work-panel'))
        self.screenshot('integrated-native-tool-snapshot')

    def test_required_input_blocks_before_any_transport_or_attempt(self):
        _,run=self.tool(required=True);self.click('[data-action="execute"]')
        self.wait("document.querySelector('#ees-work-panel [role=alert]') || document.querySelector('#ees-work-panel .ew-error')")
        self.assertEqual(self.bridge.calls,[]);self.assertEqual(self.state(run_id=run['id'])['run']['attempts'],[])

    def test_partial_failed_unknown_stay_distinct_and_never_auto_retry(self):
        for status in ('partial','failed','unknown'):
            with self.subTest(status=status):
                self.bridge.result={'status':status,'completeness':'partial' if status=='partial' else 'unknown','error':{'code':'synthetic_'+status}}
                key,run=self.tool();count=len(self.bridge.calls)
                result=asyncio.run(self.server.workflow.operations.command(self.server.user,{'action':'execute_job','run_id':run['id'],'job_id':'job-0','expected_revision':run['revision'],'request_id':str(uuid4())}))
                self.assertEqual(result['attempt']['status'],status)
                self.refresh();self.click('[data-action="tab"][data-tab="history"]')
                self.assertEqual(self.read('.ew-history [data-status]','dataset.status'),status)
                self.assertEqual(len(self.bridge.calls),count+1)
                self.assertNotEqual(self.state(run_id=run['id'])['run']['jobs']['job-0']['status'],'completed')
                self.screenshot('integrated-result-'+status)

    def test_running_transport_is_visible_and_cannot_double_execute(self):
        _,run=self.tool();self.bridge.hold.clear()
        self.click('[data-action="execute"]');self.assertTrue(self.bridge.started.wait(3))
        self.assertEqual(len(self.bridge.calls),1)
        running=self.state(run_id=run['id'])['run'];self.assertEqual(running['attempts'][0]['status'],'running')
        self.assertNotEqual(running['jobs']['job-0']['status'],'completed')
        self.assertTrue(self.read('[data-action="execute"]','disabled'))
        glyph='#ees-work-panel .ew-status:is([data-status=running],[data-status=in_progress]) > .ew-icon'
        self.wait('document.querySelector('+json.dumps(glyph)+')')
        # Observe real frames after animation readiness, without changing DOM or
        # animation state. A fixed pair of RAF callbacks can both see time zero.
        frames=self.browser.evaluate('''new Promise(resolve=>{
            const selector='''+json.dumps(glyph)+''',started=performance.now(),samples=[];
            let node=null,animation=null,first=null,replacements=0,finished=false;
            function finish(moved,reason,second=null){
                if(finished)return;finished=true;clearTimeout(deadline);
                resolve({moved,reason,elapsed_ms:performance.now()-started,replacements,first,second,samples});
            }
            const deadline=setTimeout(()=>finish(false,'animation_did_not_advance_before_deadline'),3000);
            function observe(timestamp){
                if(finished)return;
                const e=document.querySelector(selector),style=e&&getComputedStyle(e),rect=e?.getBoundingClientRect();
                const current=e?.getAnimations().find(value=>value.animationName==='ew-running'&&value.effect?.target===e);
                const visible=Boolean(e?.isConnected&&rect?.width>0&&rect.height>0&&rect.bottom>0&&rect.right>0&&
                    rect.top<innerHeight&&rect.left<innerWidth&&style.display!=='none'&&style.visibility==='visible'&&Number(style.opacity)>0);
                if(e!==node||current!==animation){if(node)replacements++;node=e;animation=current;first=null;}
                const sample={timestamp,connected:Boolean(e?.isConnected),visible,visibility:document.visibilityState,
                    reduced_motion:matchMedia('(prefers-reduced-motion: reduce)').matches,
                    name:style?.animationName,transform:style?.transform,pending:current?.pending,
                    play_state:current?.playState,current_time:typeof current?.currentTime==='number'?current.currentTime:null,
                    start_time:typeof current?.startTime==='number'?current.startTime:null,
                    rect:rect&&{x:rect.x,y:rect.y,width:rect.width,height:rect.height}};
                samples.push(sample);if(samples.length>180)samples.shift();
                const ready=visible&&sample.visibility==='visible'&&!sample.reduced_motion&&sample.name==='ew-running'&&
                    current?.playState==='running'&&!current.pending&&sample.current_time!==null;
                if(!ready)first=null;
                else if(!first)first=sample;
                else if(timestamp>first.timestamp&&sample.current_time>first.current_time&&sample.transform!==first.transform){
                    finish(true,'same_live_animation_advanced',sample);return;
                }
                requestAnimationFrame(observe);
            }
            requestAnimationFrame(observe);
        })''')
        directory=self.screenshot('integrated-running-animation')
        (directory/'integrated-running-animation.json').write_text(json.dumps(frames,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        self.assertTrue(frames['moved'],json.dumps(frames,ensure_ascii=False))
        self.assertEqual(frames['first']['name'],'ew-running');self.assertEqual(frames['second']['name'],'ew-running')
        self.assertGreater(frames['second']['current_time'],frames['first']['current_time'])
        self.assertNotEqual(frames['first']['transform'],frames['second']['transform'])
        self.browser.call('Emulation.setEmulatedMedia',{'features':[{'name':'prefers-reduced-motion','value':'reduce'}]})
        self.wait('getComputedStyle(document.querySelector('+json.dumps(glyph)+')).animationName === "none"')
        self.screenshot('integrated-running-reduced-motion')
        self.bridge.hold.set()
        self.wait("!document.querySelector('[data-action=execute]')?.disabled")
        self.assertEqual(len(self.bridge.calls),1)
        self.assertEqual(len(self.state(run_id=run['id'])['run']['attempts']),1)

    def test_revoked_tool_access_blocks_a_new_attempt_before_transport(self):
        _,run=self.tool();self.bridge.allowed=False
        self.click('[data-action="execute"]')
        self.wait("document.querySelector('#ees-work-panel')?.innerText.includes('권한')")
        self.assertEqual(self.bridge.calls,[])
        self.assertEqual(self.state(run_id=run['id'])['run']['attempts'],[])

    def test_human_confirmation_never_calls_external_tool(self):
        key=self.author();run=self.start(key);self.open_run(key,run)
        self.click('[data-action="confirm"]');self.click('[data-dialog-confirm]')
        self.wait("document.querySelector('#ees-work-panel [data-status=completed]')")
        self.assertEqual(self.bridge.calls,[])
        self.assertEqual(self.state(run_id=run['id'])['run']['jobs']['job-0']['status'],'completed')
