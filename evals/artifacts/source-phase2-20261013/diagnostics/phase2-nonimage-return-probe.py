import json, time
from pathlib import Path
from test_ees_work_figma_authoring_native import FigmaAuthoringNativeTests
name='test_native_menu_skills_returns_to_unsaved_procedure_tool_and_start_with_nonimage_draft'
FigmaAuthoringNativeTests.setUpClass()
c=FigmaAuthoringNativeTests(name)
c.setUp()
print('server_started',flush=True)
c.browser.call('Page.addScriptToEvaluateOnNewDocument', {'source': """window.__returnTrace=[];function sample(){let r=window.__eesNativeWorkV1?.captureReference();let e=document.querySelector('#ew-author-node [name=name],#ew-author-tool [name=name],#ew-procedure-name');window.__returnTrace.push({at:performance.now(),path:location.pathname,ready:window.__eesNativeDraftV1?.ready(),reference:r,field:e?.value,designer:!!document.querySelector('#ees-work-designer'),nativeDraft:window.__eesNativeDraftV1?.read(),error:document.querySelector('.ew-error')?.textContent});if(window.__returnTrace.length<6000)requestAnimationFrame(sample)};requestAnimationFrame(sample)"""})
try:
 getattr(c,name)()
 print('test_completed_without_failure',flush=True)
except Exception as e:
 print('observed_original_failure',type(e).__name__,str(e)[:220],flush=True)
start=c.browser.evaluate('window.__returnTrace.length')
c.wait('window.__returnTrace.length >= '+str(start+90))
a=c.browser.evaluate('window.__returnTrace')
Path('/tmp/phase2-nonimage-return-probe.json').write_text(json.dumps(a,ensure_ascii=False),encoding='utf-8')
last=None; changes=[]
for x in a:
 key=json.dumps({k:v for k,v in x.items() if k!='at'},sort_keys=True,ensure_ascii=False)
 if key!=last: changes.append(x);last=key
print(json.dumps(changes,ensure_ascii=False),flush=True)
c.doCleanups()
