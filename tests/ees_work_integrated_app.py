"""Complete packaged Native app gate for the integrated work contract.

One temporary DATA_DIR and a loopback synthetic model are used. Native auth,
chat/file storage, workflow APIs, worker and frontend are the built product.
No company credentials, DB or service is read. Physical CDP input drives UI;
read-only DOM evaluation inspects readiness and results. Failure evidence is
captured before browser shutdown. This is distinct from the Native fixtures.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from uuid import uuid4
from zipfile import ZipFile

import httpx
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_ees_chat_theme import ChromePipe
from ees_work_c_phase3_fullapp import SyntheticProvider


class ProductGate:
    def __init__(self, args):
        self.args = args
        self.out = args.output.resolve(); self.out.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix='ees-integrated-native-')
        self.work = Path(self.tmp.name)
        self.provider = SyntheticProvider()
        self.provider.allow_embeddings = True
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0)); self.port = listener.getsockname()[1]
        self.base = 'http://127.0.0.1:' + str(self.port)
        self.program = self.work/'program'
        with ZipFile(args.wheel) as archive:
            for member in archive.infolist():
                assert (self.program/member.filename).resolve().is_relative_to(self.program.resolve())
            archive.extractall(self.program)
        inherited = {key: value for key, value in os.environ.items() if key in {
            'PATH', 'LANG', 'LC_ALL', 'TZ', 'TMPDIR', 'TEMP', 'TMP', 'SYSTEMROOT', 'WINDIR',
            'LD_LIBRARY_PATH', 'SSL_CERT_FILE', 'SSL_CERT_DIR'}}
        self.environment = dict(inherited, DATA_DIR=str(self.work/'data'),
            DATABASE_URL='sqlite:///' + str(self.work/'data/webui.db'),
            WEBUI_SECRET_KEY=secrets.token_urlsafe(48), PYTHONPATH=str(self.program),
            OFFLINE_MODE='true', HF_HUB_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1',
            TRANSFORMERS_OFFLINE='1', ANONYMIZED_TELEMETRY='false', DO_NOT_TRACK='true',
            ENABLE_OLLAMA_API='false', OLLAMA_API_KEY='', OLLAMA_BASE_URL='http://127.0.0.1:1',
            ENABLE_OPENAI_API='true', OPENAI_API_BASE_URL=self.provider.base+'/v1',
            OPENAI_API_BASE_URLS=self.provider.base+'/v1', OPENAI_API_KEY='synthetic-local-only',
            OPENAI_API_KEYS='synthetic-local-only', ENABLE_VALVE_ENCRYPTION='true',
            RAG_EMBEDDING_ENGINE='openai', RAG_OPENAI_API_BASE_URL=self.provider.base+'/v1',
            RAG_OPENAI_API_KEY='synthetic-local-only', RAG_EMBEDDING_MODEL='synthetic-embedding',
            ENABLE_VERSION_UPDATE_CHECK='false', ENABLE_PIP_INSTALL_FRONTMATTER_REQUIREMENTS='false',
            ENABLE_OTEL='false', WEBUI_ADMIN_EMAIL='', WEBUI_ADMIN_PASSWORD='',
            DEFAULT_MODELS='c3-synthetic-model', ENABLE_TITLE_GENERATION='false',
            ENABLE_TAGS_GENERATION='false', ENABLE_FOLLOW_UP_GENERATION='false')
        (self.work/'data').mkdir(mode=0o700)
        self.client = httpx.Client(base_url=self.base, trust_env=False, timeout=20)
        self.server = self.log = self.browser = None
        self.headers = {}
        self.report = {'time': datetime.now(timezone.utc).isoformat(), 'scope': __doc__,
            'source_commit': subprocess.check_output(['git','rev-parse','HEAD'], text=True, encoding='utf-8').strip(),
            'source_dirty': bool(subprocess.check_output(['git','status','--porcelain'], text=True, encoding='utf-8').strip()),
            'wheel': args.wheel.name, 'wheel_sha256': hashlib.sha256(args.wheel.read_bytes()).hexdigest(),
            'steps': [], 'status': 'running'}

    def record(self, name, **fields):
        item = {'name': name, **fields}; self.report['steps'].append(item)
        print(json.dumps(item, ensure_ascii=False), flush=True)
        self.write_report()

    def write_report(self):
        (self.out/'report.json').write_text(json.dumps(self.report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

    def launch(self):
        self.log = (self.work/'native-server.log').open('a', encoding='utf-8')
        self.server = subprocess.Popen([sys.executable, '-c', 'from open_webui import app; app()',
            'serve', '--host', '127.0.0.1', '--port', str(self.port)], cwd=self.work,
            env=self.environment, stdout=self.log, stderr=subprocess.STDOUT)
        deadline = time.monotonic()+45
        while time.monotonic()<deadline:
            if self.server.poll() is not None:
                raise RuntimeError('Native CLI exited; sanitized local startup summary available')
            try:
                if self.client.get('/ready').status_code==200:
                    return
            except httpx.ConnectError:
                pass
            time.sleep(.2)
        raise RuntimeError('Native CLI readiness exceeded 45s')

    def stop_server(self):
        if self.server and self.server.poll() is None:
            self.server.terminate()
            try: self.server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.server.kill(); self.server.wait(timeout=5)
        if self.log: self.log.close(); self.log=None

    def api(self, path, body=None, *, method=None, expected=200, headers=None):
        response = self.client.request(method or ('POST' if body is not None else 'GET'), path,
            headers=headers if headers is not None else self.headers, json=body)
        assert response.status_code==expected, (path, response.status_code, response.text[:500])
        value=response.json()
        if expected==200: assert not isinstance(value,dict) or value.get('ok') is not False, value
        return value

    def wait(self, expression, timeout=12000):
        # Short read-only CDP evaluations keep the logical bound independent
        # of ChromePipe's per-command deadline; no DOM state is manufactured.
        deadline=time.monotonic()+timeout/1000
        while True:
            if self.browser.evaluate('(()=>{try{return Boolean('+expression+');}catch(e){return false;}})()'):
                return
            assert time.monotonic()<deadline,'Readiness failed: '+expression
            time.sleep(0.05)

    def completed_chat(self, chat_id, expected_count):
        deadline=time.monotonic()+12
        while True:
            chat=self.api('/api/v1/chats/'+chat_id)['chat']
            messages=list(chat.get('history',{}).get('messages',{}).values())
            if len(messages)==expected_count and all(m.get('done') for m in messages if m.get('role')=='assistant'):
                return chat
            assert time.monotonic()<deadline,'Native message persistence did not finish'
            time.sleep(0.05)

    def click(self, selector, text=None):
        element = ('document.querySelector('+json.dumps(selector)+')' if text is None else
            '[...document.querySelectorAll('+json.dumps(selector)+')].find(e=>e.getClientRects().length&&(e.innerText.trim()==='+json.dumps(text)+'||e.getAttribute("aria-label")==='+json.dumps(text)+'))')
        expression='''(async()=>{await document.fonts.ready;return await new Promise(resolve=>{
const end=performance.now()+9000;let last='',same=0;function check(){const e=ELEMENT;
e?.scrollIntoView({block:'center'});const r=e?.getBoundingClientRect();const key=r&&[r.x,r.y,r.width,r.height].join();
same=r&&key===last&&r.width>0&&r.height>0&&!e.disabled&&e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))?same+1:0;
last=key;if(same>=3)return resolve({x:r.x+r.width/2,y:r.y+r.height/2});
if(performance.now()>end)return resolve(null);requestAnimationFrame(check)}check()})})()'''.replace('ELEMENT',element)
        point=self.browser.evaluate(expression); assert point, 'Not clickable: '+selector
        for kind in ('mousePressed','mouseReleased'):
            self.browser.call('Input.dispatchMouseEvent',dict(type=kind,button='left',clickCount=1,**point))

    def type(self, selector, value):
        self.click(selector)
        for kind in ('keyDown','keyUp'):
            self.browser.call('Input.dispatchKeyEvent',{'type':kind,'key':'a','code':'KeyA','windowsVirtualKeyCode':65,'modifiers':2})
        self.browser.call('Input.insertText',{'text':value})

    def navigate(self, path):
        self.browser.call('Page.navigate',{'url':self.base+path})
        self.wait('document.readyState==="complete"')

    def capture(self, name):
        if not self.browser: return
        self.browser.evaluate('(async()=>{await document.fonts.ready;await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));return true})()')
        png=self.browser.call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False})['data']
        (self.out/(name+'.png')).write_bytes(base64.b64decode(png))
        details=self.browser.evaluate('''(()=>({path:location.pathname,ready:document.readyState,
fonts:document.fonts.status,body_flags:{...document.body.dataset},viewport:[innerWidth,innerHeight],active:(()=>{const e=document.activeElement;return e?{tag:e.tagName,id:e.id,text:e.textContent?.slice(0,100),html:e.outerHTML.slice(0,1000)}:null})(),
text:document.body.innerText.slice(0,16000),elements:[...document.querySelectorAll('#ees-work-entry,#ees-work-panel,#ees-work-designer,#chat-container,#chat-input,dialog')].map(e=>({id:e.id,tag:e.tagName,
rect:(()=>{const r=e.getBoundingClientRect();return{x:r.x,y:r.y,width:r.width,height:r.height}})(),
font:getComputedStyle(e).fontFamily,display:getComputedStyle(e).display,overflow:getComputedStyle(e).overflow}))}))()''')
        details['native_structure']=self.browser.evaluate("(()=>Object.fromEntries(['[data-ees-native-toolbar]','#message-input-container','#sidebar'].map(selector=>[selector,document.querySelector(selector)?.outerHTML.slice(0,20000)])))()")
        details['native_empty_headings']=self.browser.evaluate("[...document.querySelectorAll('#chat-container h1,#chat-container h2')].map(e=>({html:e.outerHTML,parent:e.parentElement?.outerHTML.slice(0,6000)}))")
        details['errors']=[{'method':event.get('method'),'details':event.get('params',{}).get('exceptionDetails',{}).get('exception',{}).get('description','')} for event in self.browser.events if event.get('method')=='Runtime.exceptionThrown']
        details['requests']=[{'path':event['params']['response']['url'].split(self.base)[-1].split('?')[0],'status':event['params']['response']['status']} for event in self.browser.events if event.get('method')=='Network.responseReceived' and '/api/ees-work/' in event['params']['response'].get('url','')]
        (self.out/(name+'.json')).write_text(json.dumps(details,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

    def setup(self):
        self.launch()
        credentials={'name':'통합 검증 관리자','email':uuid4().hex+'@example.test','password':secrets.token_urlsafe(32)}
        session=self.api('/api/v1/auths/signup',credentials); assert session['role']=='admin'
        self.headers={'Authorization':'Bearer '+session['token']}
        empty=self.api('/api/ees-work/workspace'); assert not empty.get('workflows') and not empty.get('runs')
        self.record('empty Native installation', workflows=0,runs=0)
        self.api('/api/v1/users/user/settings/update',{'ui':{'language':'ko-KR','showChangelog':False,'models':['c3-synthetic-model']}})
        models = self.api('/api/models')
        self.record('Native model availability', models=[{'id': item.get('id'), 'direct': item.get('direct'),
            'owned_by': item.get('owned_by')} for item in models.get('data', [])])
        self.browser=ChromePipe(str(self.args.chrome.resolve()),str(self.work/'chrome'),font_wheel=self.args.wheel)
        self.browser.navigate('about:blank'); self.browser.call('Runtime.enable'); self.browser.call('Network.enable')
        self.browser.call('Emulation.setDeviceMetricsOverride',{'width':1920,'height':1080,'deviceScaleFactor':1,'mobile':False})
        self.browser.call('Page.addScriptToEvaluateOnNewDocument',{'source':
            'localStorage.setItem("token",'+json.dumps(session['token'])+');localStorage.setItem("locale","ko-KR");localStorage.setItem("version","0.11.3+ees.13");'})
        self.navigate('/'); self.wait('!!document.querySelector("#ees-work-entry")&&!!document.querySelector("#chat-input")')
        self.wait('!document.querySelector("#ees-work-panel")?.innerText.includes("불러오는 중")')
        self.capture('a0-empty')
        self.record('actual built Native render', viewport=[1920,1080])

    def run(self):
        self.setup()
        # Detailed work authoring/runtime/UI assertions are deliberately kept
        # in one gate so screenshots always correspond to the tested wheel.
        integrated_flow(self)
        self.report['status']='passed'; self.write_report()

    def close(self):
        if self.browser: self.browser.close()
        self.stop_server(); self.client.close(); self.provider.close(); self.tmp.cleanup()


def integrated_flow(gate):
    g=gate
    # All business writes in this flow are actual visible user controls.
    g.click('[data-action="mode"][data-mode="author"]')
    g.click('[data-author-action="create"]')
    g.type('#ees-work-dialog input[name="name"]','합성 배포 자료 확인')
    g.click('#ees-work-dialog [data-dialog-confirm]')
    g.wait('!!document.querySelector(\'[data-author-action="add_stage"]\')')
    g.click('[data-author-action="add_stage"]')
    g.type('#ew-author-node input[name="name"]','자료 검토')
    g.click('[data-author-action="node"][data-id=""]')
    g.click('[data-author-action="add_job"]')
    g.type('#ew-author-node input[name="name"]','사람의 근거 확인')
    g.click('[data-author-action="input_add"]')
    g.type('#ees-work-dialog input[name="name"]','확인할 자료')
    g.type('#ees-work-dialog input[name="id"]','evidence_note')
    g.click('#ees-work-dialog input[name="required"]')
    g.click('#ees-work-dialog [data-dialog-confirm]')
    g.click('[data-author-action="save"]')
    g.wait('!document.querySelector(\'[data-author-action="validate"]\')?.disabled')
    g.capture('b3-saved-authoring')
    state=g.api('/api/ees-work/workspace')
    workflow=next(item for item in state['workflows'] if item['name']=='합성 배포 자료 확인')
    identifier=workflow['id']
    g.click('[data-author-action="validate"]')
    g.wait('!!document.querySelector(\'[data-author-action="publish"]\')')
    g.click('[data-author-action="publish"]')
    g.wait("document.activeElement?.matches('#ees-work-dialog [data-dialog-cancel]')")
    assert g.browser.evaluate("(()=>{const r=document.querySelector('#ees-work-dialog').getBoundingClientRect();return Math.abs(r.x+r.width/2-innerWidth/2)<2&&Math.abs(r.y+r.height/2-innerHeight/2)<2})()"), 'confirmation dialog must be centered'
    g.capture('publish-confirmation-cancel-focus')
    g.click('#ees-work-dialog [data-dialog-confirm]')
    g.wait('document.querySelector("#ees-work-designer")?.innerText.includes("게시 v1")')
    published=g.api('/api/ees-work/workspace?workflow_id='+identifier)['workflow']
    assert published['published_version']==1
    g.capture('b2-published')
    g.record('physical authoring save validate publish',workflow_id=identifier,version=1)
    g.click('[data-action="mode"][data-mode="work"]')
    g.click('[data-action="workflow"][data-workflow-id="'+identifier+'"]')
    g.click('[data-action="start_run"]')
    g.click('#ees-work-dialog [data-dialog-confirm]')
    g.wait('!!document.querySelector(\'[data-action="job"]\')')
    state=g.api('/api/ees-work/workspace?workflow_id='+identifier)
    run=state['runs'][0];run_id=run['id']
    job_id=next(key for key,node in run['definition']['nodes'].items() if node['type']=='j')
    g.click('[data-action="job"][data-job-id="'+job_id+'"]')
    g.type('#ees-work-inputs [name="evidence_note"]','개발용 합성 근거 v1')
    g.click('[data-action="save_inputs"]')
    g.wait('!document.querySelector(\'[data-action="save_inputs"]\')?.disabled')
    saved=g.api('/api/ees-work/workspace?run_id='+run_id)['run']
    assert saved['inputs']['evidence_note']=='개발용 합성 근거 v1'
    assert saved['jobs'][job_id]['status']!='completed'
    g.capture('a1-input-saved-not-complete')
    g.click('[data-action="confirm"]')
    g.wait("document.activeElement?.matches('#ees-work-dialog [data-dialog-cancel]')")
    g.browser.call('Input.dispatchKeyEvent',{'type':'keyDown','key':'Escape','windowsVirtualKeyCode':27})
    g.browser.call('Input.dispatchKeyEvent',{'type':'keyUp','key':'Escape','windowsVirtualKeyCode':27})
    assert g.api('/api/ees-work/workspace?run_id='+run_id)['run']['jobs'][job_id]['status']!='completed'
    g.click('[data-action="confirm"]');g.click('#ees-work-dialog [data-dialog-confirm]')
    g.wait('!!document.querySelector("#ees-work-panel .ew-status[data-status=completed]")')
    complete=g.api('/api/ees-work/workspace?run_id='+run_id)['run']
    assert complete['jobs'][job_id]['status']=='completed',complete['jobs'][job_id]
    assert len(complete['attempts'])==1
    g.capture('a1-human-complete')
    g.record('run input save cancel confirmation and actual completion',run_id=run_id,attempts=1,version=complete['version'])
    # Native text entry/send is physical; saving or completion HTTP calls are
    # never injected by the test. Model HTTP content alone is synthetic.
    question='개발용 합성 대화 저장 확인'
    g.type('#chat-input',question)
    g.click('#send-message-button')
    g.wait('location.pathname.startsWith("/c/")&&document.querySelector("#chat-container")?.innerText.includes("합성 모델 응답")',20000)
    chat_id=g.browser.evaluate('location.pathname.split("/").at(-1)')
    chat=g.completed_chat(chat_id,2)
    messages=list(chat['history']['messages'].values())
    assert len([item for item in messages if item.get('role')=='user' and item.get('content')==question])==1
    assert len([item for item in messages if item.get('role')=='assistant' and '합성 모델 응답' in str(item.get('content'))])==1
    g.capture('native-chat-saved')
    g.navigate('/c/'+chat_id);g.wait('document.querySelector("#chat-container")?.innerText.includes("合成")'.replace('合成','합성 모델 응답'))
    assert g.api('/api/v1/chats/'+chat_id)['chat']['history']==chat['history']
    g.record('Native physical send and storage reload',saved_messages=len(messages),chat_id=chat_id,model_boundary='loopback synthetic HTTP only')
    chat = native_attachment_flow(g, chat_id)
    g.browser.call('Emulation.setDeviceMetricsOverride',{'width':1100,'height':800,'deviceScaleFactor':1,'mobile':False})
    g.capture('native-narrow')
    assert g.browser.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'horizontal document overflow'
    g.browser.call('Emulation.setEmulatedMedia',{'features':[{'name':'prefers-reduced-motion','value':'reduce'}]})
    assert g.browser.evaluate("matchMedia('(prefers-reduced-motion:reduce)').matches")
    assert g.browser.evaluate("[...document.querySelectorAll('#ees-work-entry *,#ees-work-panel *')].every(e=>{const s=getComputedStyle(e);return s.animationName==='none'||s.animationDuration.split(',').every(v=>parseFloat(v)<=0.001)})"), 'work UI must respect reduced motion'
    g.capture('native-reduced-motion')
    g.stop_server();g.launch()
    assert g.api('/api/ees-work/workspace?run_id='+run_id)['run']['attempts']==complete['attempts']
    assert g.api('/api/v1/chats/'+chat_id)['chat']['history']==chat['history']
    g.record('Native and work restart persistence',chat_preserved=True,attempts_preserved=True)


def native_attachment_flow(g, chat_id):
    """Physical Native chooser/send, then read-only file and chat verification."""
    sample=g.out/'synthetic-native-upload.txt'
    content='Synthetic attachment for isolated Native upload verification. No company data.\n'
    sample.write_text(content,encoding='utf-8')
    g.browser.call('Page.setInterceptFileChooserDialog',{'enabled':True})
    g.browser.events.clear()
    g.click('#input-menu-button')
    g.click('button,[role="menuitem"],a','파일 업로드')
    deadline=time.monotonic()+10
    chooser=next((e for e in g.browser.events if e.get('method')=='Page.fileChooserOpened'),None)
    while chooser is None:
        g.browser.events.append(g.browser.receive(deadline))
        chooser=next((e for e in g.browser.events if e.get('method')=='Page.fileChooserOpened'),None)
    assert chooser['params']['mode']=='selectMultiple'
    g.browser.call('DOM.setFileInputFiles',{'backendNodeId':chooser['params']['backendNodeId'],'files':[str(sample)]})
    g.wait('document.querySelector("#message-input-container")?.innerText.includes("synthetic-native-upload.txt")')
    deadline=time.monotonic()+15;upload=None
    while upload is None:
        posts={e['params']['requestId'] for e in g.browser.events if e.get('method')=='Network.requestWillBeSent'
            and e['params']['request'].get('method')=='POST' and '/api/v1/files/' in e['params']['request'].get('url','')}
        completed={e['params']['requestId'] for e in g.browser.events if e.get('method')=='Network.loadingFinished'}
        upload=next((e['params'] for e in g.browser.events if e.get('method')=='Network.responseReceived' and e['params']['requestId'] in posts&completed),None)
        if upload is None:g.browser.events.append(g.browser.receive(deadline))
    assert upload['response']['status']==200
    uploaded=json.loads(g.browser.call('Network.getResponseBody',{'requestId':upload['requestId']})['body'])
    deadline=time.monotonic()+15
    status=g.api('/api/v1/files/'+uploaded['id']+'/process/status')['status']
    while status not in ('completed','failed') and time.monotonic()<deadline:
        time.sleep(0.25);status=g.api('/api/v1/files/'+uploaded['id']+'/process/status')['status']
    if status!='completed':
        file_state=g.api('/api/v1/files/'+uploaded['id'])
        g.record('Native attachment processing failure',status=status,file_state=file_state,
                 provider_calls=g.provider.calls)
        log=(g.work/'native-server.log').read_text(encoding='utf-8',errors='replace')[-24000:]
        for secret in (g.environment['WEBUI_SECRET_KEY'],g.headers.get('Authorization','')):
            if secret:log=log.replace(secret,'[synthetic credential redacted]')
        (g.out/'attachment-processing-failure.log').write_text(log,encoding='utf-8')
    assert status=='completed',status
    assert content.strip() in g.api('/api/v1/files/'+uploaded['id']+'/data/content')['content']
    g.capture('native-file-upload')
    g.browser.call('Page.setInterceptFileChooserDialog',{'enabled':False})
    question='이 합성 첨부 파일을 확인해 줘.'
    answer='합성 첨부 응답: Native 파일과 대화 저장 확인'
    g.provider.native_content=answer
    g.browser.events.clear();g.type('#chat-input',question);g.click('#send-message-button')
    g.wait('document.querySelector("#chat-container")?.innerText.includes('+json.dumps(answer)+')',20000)
    chat=g.completed_chat(chat_id,4)
    matches=[m for m in chat['history']['messages'].values() if m.get('role')=='user' and m.get('content')==question]
    assert len(matches)==1
    files=matches[0].get('files',[])
    assert any(f.get('id')==uploaded['id'] or f.get('file',{}).get('id')==uploaded['id'] for f in files)
    g.capture('native-attachment-saved')
    g.navigate('/c/'+chat_id)
    g.wait('document.querySelector("#chat-container")?.innerText.includes('+json.dumps(answer)+')&&document.querySelector("#chat-container")?.innerText.includes("synthetic-native-upload.txt")')
    assert g.api('/api/v1/chats/'+chat_id)['chat']['history']==chat['history']
    g.capture('native-attachment-restored')
    g.record('Native attachment chooser upload process send reload',file_id=uploaded['id'],chat_id=chat_id,
        model_boundary='Only model response and embedding vectors are loopback synthesis')
    return chat



def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel',type=Path,required=True)
    parser.add_argument('--chrome',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); gate=ProductGate(args)
    try:
        gate.run()
    except BaseException as error:
        gate.report['status']='failed'; gate.report['failure']={'type':type(error).__name__,'message':str(error)[:1200]}
        try: gate.capture('failure')
        except Exception as capture_error: gate.report['capture_error']=type(capture_error).__name__+': '+str(capture_error)[:300]
        gate.write_report(); raise
    finally:
        gate.close()


if __name__=='__main__':
    main()
