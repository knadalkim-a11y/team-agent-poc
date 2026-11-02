import base64,json,sys,unittest,hashlib,os
from pathlib import Path
ROOT=Path('/workspace/scratch/b1afafbe4fcd/repo')
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from ees_work_integrated_fixture import IntegratedNativeCase
OUT=Path('/workspace/scratch/b1afafbe4fcd/operations-diagnosis-20261030')
class Diagnose(IntegratedNativeCase):
 def capture_case(self,label):
  self.wait("!document.querySelector('[data-ees-motion=opening],[data-ees-motion=closing]')")
  self.browser.evaluate('document.fonts.ready.then(()=>true)')
  d=self.browser.evaluate("""(()=>{const p=document.querySelector('#ees-work-panel'),r=p.getBoundingClientRect();return {text:p.innerText,overview:!!p.querySelector('.ew-operation-overview'),stage:!!document.querySelector('#ees-work-panel.ew-vd'),oldStart:!!p.querySelector('#ees-work-start'),stageRows:p.querySelectorAll('.ew-operation-stage').length,jobRows:p.querySelectorAll('[data-stage-job]').length,rect:{x:r.x,y:r.y,width:r.width,height:r.height},reference:window.__eesNativeWorkV1.captureReference()};})()""")
  d['label']=label
  png=base64.b64decode(self.browser.call('Page.captureScreenshot',{'format':'png','clip':{**d['rect'],'scale':1},'captureBeyondViewport':True})['data'])
  (OUT/(label+'.png')).write_bytes(png)
  d['png_sha256']=hashlib.sha256(png).hexdigest()
  self.observations.append(d)
  (OUT/'observations.json').write_text(json.dumps(self.observations,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
  print(json.dumps({k:v for k,v in d.items() if k not in ('rect','reference','png_sha256')},ensure_ascii=False),flush=True)
 def open_key(self,key):
  self.open_sidebar();self.refresh()
  selector='[data-action="workflow"][data-workflow-id="'+key+'"]'
  self.wait('document.querySelector('+json.dumps(selector)+')')
  self.click(selector)
  self.wait('window.__eesNativeWorkV1.captureReference()?.workflow_id === '+json.dumps(key))
 def test_render_paths(self):
  self.observations=[]
  self.browser.call('Emulation.setDeviceMetricsOverride',{'width':1920,'height':1080,'deviceScaleFactor':1,'mobile':False})
  published=self.author(name='검증용 게시 절차')
  created=self.command('create_workflow',name='검증용 미게시 수시 절차',system_id='EMS')
  draftkey=created['workflow_id'];definition=created['workflow']['draft'];root=next(iter(definition['nodes']))
  definition['nodes'][root]['children']=['draft-stage']
  definition['nodes']['draft-stage']={'id':'draft-stage','type':'t','name':'미게시 점검 단계','parent':root,'children':['draft-job'],'deps':[]}
  definition['nodes']['draft-job']={'id':'draft-job','type':'j','name':'미게시 확인 작업','parent':'draft-stage','children':[],'deps':[],'mode':'human','inputs':[],'result_block':'human_confirm','instructions':'합성 확인 내용'}
  self.command('save_draft',workflow_id=draftkey,expected_revision=1,definition=definition)
  periodic=self.command('create_workflow',name='검증용 미게시 배포 점검',system_id='EMS',template_id='delivery_review')['workflow_id']
  self.open_key(published)
  self.wait("document.querySelector('.ew-operation-overview')")
  self.capture_case('published-new-overview')
  self.click('[data-action=stage_open][data-node-id=stage]')
  self.wait("document.querySelector('#ees-work-panel.ew-vd')")
  self.capture_case('published-new-stage')
  self.open_key(draftkey)
  self.wait("document.querySelector('#ees-work-start')")
  self.capture_case('unpublished-on-demand-old-start')
  self.open_key(periodic)
  self.wait("document.querySelector('#ees-work-panel')?.innerText.includes('게시한 절차 버전으로 새 진행 건을 시작합니다.')")
  self.capture_case('unpublished-periodic-old-overview')
  with self.server.workflow._db() as db:
   self.assertEqual(db.execute('SELECT COUNT(*) FROM work_runs').fetchone()[0],0)
  self.assertEqual(self.bridge.calls,[])
if __name__=='__main__':
 unittest.main(verbosity=2)
