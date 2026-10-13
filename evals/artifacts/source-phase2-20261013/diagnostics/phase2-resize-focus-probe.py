import json,sys,tempfile
from pathlib import Path
sys.path.insert(0,'/workspace/scratch/f5cd50d81fb4/team-agent-poc-phase2/tests')
from test_ees_chat_theme import ChromePipe
source=Path('/workspace/scratch/f5cd50d81fb4/open-webui-phase2-1/src/lib/components/ees/EesShell.svelte').read_text()
handler=source[source.index('function resizeStart(e) {'):source.index('\n\tfunction resizeMove',source.index('function resizeStart(e) {'))]
chrome='/workspace/scratch/f5cd50d81fb4/c18-review-tools/chrome-headless-shell-linux64/chrome-headless-shell'
results=[]
with tempfile.TemporaryDirectory(prefix='ees-source-focus-') as profile:
 browser=ChromePipe(chrome,profile)
 try:
  browser.navigate('about:blank')
  for fixed,key,code in [(False,'End',35),(True,'End',35),(True,'Home',36)]:
   js=handler if fixed else handler.replace('e.currentTarget.focus({ preventScroll: true });','')
   browser.evaluate('''(()=>{document.body.innerHTML='<input id="composer" value="draft"><div id="resize" tabindex="0" role="separator" style="position:absolute;left:200px;top:80px;width:20px;height:300px;background:#ddd"></div>';let resizing=false,dragX=0,dragWidth=480,panelWidth=480;window.keys=[];window.width=480;'''+js+'''document.querySelector('#resize').addEventListener('pointerdown',resizeStart);document.querySelector('#resize').addEventListener('keydown',e=>{window.keys.push(e.key);const next={End:720,Home:400}[e.key];if(next!==undefined){e.preventDefault();window.width=next;}});document.querySelector('#composer').focus();return true;})()''')
   for kind in ('mousePressed','mouseReleased'):
    browser.call('Input.dispatchMouseEvent',{'type':kind,'x':210,'y':150,'button':'left','buttons':int(kind=='mousePressed'),'clickCount':1})
   for kind in ('keyDown','keyUp'):
    browser.call('Input.dispatchKeyEvent',{'type':kind,'key':key,'code':key,'windowsVirtualKeyCode':code,'nativeVirtualKeyCode':code})
   data=browser.evaluate('({active:document.activeElement.id,keys:window.keys,width:window.width})')
   results.append({'fixed':fixed,'key':key,**data})
 finally:browser.close()
assert results==[{'fixed':False,'key':'End','active':'composer','keys':[],'width':480},{'fixed':True,'key':'End','active':'resize','keys':['End'],'width':720},{'fixed':True,'key':'Home','active':'resize','keys':['Home'],'width':400}],results
output={'kind':'isolated source-handler CDP probe; not full product acceptance','source':'EesShell.svelte resizeStart','results':results}
Path('/workspace/scratch/f5cd50d81fb4/phase2-resize-focus-probe.json').write_text(json.dumps(output,indent=2)+'\n')
print(json.dumps(output))
