"""Complete packaged Native app gate for the integrated work contract.

One temporary DATA_DIR and a loopback synthetic model are used. Native auth,
chat/file storage, workflow APIs, worker and frontend are the built product.
No company credentials, DB or service is read. Physical CDP input drives UI;
read-only DOM evaluation inspects readiness and results. Failure evidence is
captured before browser shutdown. This is distinct from the Native fixtures.
This gate was reconstructed after workspace loss from the committed base and
observed failures. It is not claimed byte-identical to the lost c144 gate.
"""
import argparse
import ast
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
import re
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


WORK_REFERENCE_PREFIX = 'EES Work context (read-only reference): '


def historical_request_route(payload, question, query_template):
    """Exact pinned retrieval task only; main and unknown calls keep guards."""
    messages=payload.get('messages',[])
    contents=[item.get('content') for item in messages]
    exact=any(item.get('role')=='user' and item.get('content')==question for item in messages)
    reference=any(item.get('role')=='system' and isinstance(item.get('content'),str)
        and item['content'].startswith(WORK_REFERENCE_PREFIX) for item in messages)
    route={'kind':'unknown','roles':[item.get('role') for item in messages],
        'message_count':len(messages),'stream':payload.get('stream'),'tool_count':len(payload.get('tools') or []),
        'exact_question':exact,'has_historical_reference':reference,
        'question_in_content':any(isinstance(value,str) and question in value for value in contents),
        'contents':[{'type':type(value).__name__,'sha256':hashlib.sha256(json.dumps(value,ensure_ascii=False).encode()).hexdigest(),
            'prefix':value[:160] if isinstance(value,str) else None} for value in contents]}
    if reference or exact: route['kind']='historical_main'
    elif route['roles']==['user'] and payload.get('stream') is False and not payload.get('tools'):
        pattern=re.escape(query_template).replace(re.escape('{{CURRENT_DATE}}'),r'\d{4}-\d{2}-\d{2}')
        pattern=pattern.replace(re.escape('{{MESSAGES:END:6}}'),r'[\s\S]*')
        if isinstance(contents[0],str) and re.fullmatch(pattern,contents[0]): route['kind']='native_retrieval_query'
    return route


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
            'gate_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'execution':{'python':sys.version.split()[0],'argv':sys.argv,'chrome':str(args.chrome.resolve()),
                'reconstructed_after_workspace_loss':True,'prior_lost_gate_byte_identity_claimed':False},
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
        focus=self.browser.evaluate('(()=>{const target=document.querySelector('+json.dumps(selector)+'),active=document.activeElement;'
            'return {matches:!!target&&(target===active||target.contains(active)),tag:active?.tagName,id:active?.id,name:active?.getAttribute("name")};})()')
        assert focus['matches'],('Physical click did not focus the current input',selector,focus)
        for kind in ('keyDown','keyUp'):
            self.browser.call('Input.dispatchKeyEvent',{'type':kind,'key':'a','code':'KeyA','windowsVirtualKeyCode':65,'modifiers':2})
        self.browser.call('Input.insertText',{'text':value})

    def select(self, selector, value):
        """Select an enabled Native option with keyboard input."""
        index=self.browser.evaluate('[...document.querySelector('+json.dumps(selector)+').options].filter(o=>!o.disabled).findIndex(o=>o.value==='+json.dumps(value)+')')
        assert index>=0,('Requested choice must be enabled',selector,value)
        self.click(selector)
        for kind in ('keyDown','keyUp'):self.browser.call('Input.dispatchKeyEvent',{'type':kind,'key':'Home','windowsVirtualKeyCode':36})
        for _ in range(index):
            for kind in ('keyDown','keyUp'):self.browser.call('Input.dispatchKeyEvent',{'type':kind,'key':'ArrowDown','windowsVirtualKeyCode':40})
        for kind in ('keyDown','keyUp'):self.browser.call('Input.dispatchKeyEvent',{'type':kind,'key':'Enter','windowsVirtualKeyCode':13})
        self.wait('document.querySelector('+json.dumps(selector)+')?.value==='+json.dumps(value))

    def navigate(self, path):
        before=self.browser.evaluate('performance.timeOrigin')
        target=self.base+path
        navigation=self.browser.call('Page.navigate',{'url':target})
        assert navigation.get('loaderId') and not navigation.get('errorText'),navigation
        deadline=time.monotonic()+12
        while True:
            observed=self.browser.evaluate('({ready:document.readyState,origin:performance.timeOrigin,url:location.href})')
            if observed['ready']=='complete' and observed['origin']!=before and observed['url']==target: break
            assert time.monotonic()<deadline,('Requested new document was not ready',observed)
            time.sleep(.05)
        frame=self.browser.call('Page.getFrameTree')['frameTree']['frame']
        assert frame['loaderId']==navigation['loaderId'],'Requested document loader has not committed'

    def wait_work_ready(self, *, workflow_id=None, run_id=None, attempt_id=None, selector=None):
        # Native chat and document/fonts can finish before Work state restoration.
        # Reading this public reference does not mutate UI or business state.
        expression='''(()=>{const p=document.querySelector('#ees-work-panel'),c=document.querySelector('#ees-work-content');
const e=SELECTOR?document.querySelector(SELECTOR):null;return {
loaded:!!p&&!p.hidden&&!!p.getClientRects().length&&!!c,
busy:p?.getAttribute('aria-busy')!=='false',loading:!!c?.querySelector('.ew-empty[role=status]'),
error:!!c?.querySelector('.ew-error[role=alert]'),reference:window.__eesNativeWorkV1?.captureReference()||{},
selector_visible:!SELECTOR||!!e?.getClientRects().length};})()'''.replace('SELECTOR',json.dumps(selector))
        expected={key:value for key,value in {'workflow_id':workflow_id,'run_id':run_id,'attempt_id':attempt_id}.items() if value is not None}
        deadline=time.monotonic()+15
        while True:
            observed=self.browser.evaluate(expression)
            if (observed['loaded'] and not observed['busy'] and not observed['loading'] and not observed['error']
                    and observed['selector_visible'] and all(observed['reference'].get(key)==value for key,value in expected.items())):
                return observed
            assert time.monotonic()<deadline,('Work panel did not settle',expected,observed)
            time.sleep(.05)

    def capture(self, name):
        if not self.browser: return
        # Persist the first transport failure before page CDP or shutdown can
        # obscure it. The central Native-chat gate inherits this same collector.
        details={'browser':self.browser.diagnostics()}
        if not self.browser.session:
            details['page_capture']='unavailable_no_attached_session'
        (self.out/(name+'.json')).write_text(json.dumps(details,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        if name=='failure':
            self.report['browser_diagnostics']=details['browser'];self.write_report()
        if not self.browser.session:return
        self.browser.evaluate('(async()=>{await document.fonts.ready;await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));return true})()')
        png=self.browser.call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False})['data']
        (self.out/(name+'.png')).write_bytes(base64.b64decode(png))
        details.update(self.browser.evaluate('''(()=>({path:location.pathname,ready:document.readyState,
fonts:document.fonts.status,body_flags:{...document.body.dataset},viewport:[innerWidth,innerHeight],active:(()=>{const e=document.activeElement;return e?{tag:e.tagName,id:e.id,text:e.textContent?.slice(0,100),html:e.outerHTML.slice(0,1000)}:null})(),
text:document.body.innerText.slice(0,16000),elements:[...document.querySelectorAll('#ees-work-entry,#ees-work-panel,#ees-work-designer,#chat-container,#chat-input,dialog')].map(e=>({id:e.id,tag:e.tagName,
rect:(()=>{const r=e.getBoundingClientRect();return{x:r.x,y:r.y,width:r.width,height:r.height}})(),
font:getComputedStyle(e).fontFamily,display:getComputedStyle(e).display,overflow:getComputedStyle(e).overflow}))}))()'''))
        details['work_state']=self.browser.evaluate('''(()=>{const p=document.querySelector('#ees-work-panel'),c=document.querySelector('#ees-work-content'),t=document.querySelector('#ees-review-text');return {busy:p?.getAttribute('aria-busy'),loading:!!c?.querySelector('.ew-empty[role=status]'),reference:window.__eesNativeWorkV1?.captureReference(),review:t?{readOnly:t.readOnly,revision:t.dataset.reviewRevision,value:t.value}:null,open_history:[...document.querySelectorAll('.ew-history[open]')].map(e=>e.dataset.key),scroll:c?{top:c.scrollTop,height:c.clientHeight,total:c.scrollHeight,width:c.clientWidth,total_width:c.scrollWidth}:null};})()''')
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
        figma_delta_flow(self)
        self.report['status']='passed'; self.write_report()

    def close(self):
        if self.browser:
            self.browser.close()
            self.report['browser_cleanup_diagnostics']=self.browser.final_diagnostics
            self.write_report()
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
    g.wait('!!document.querySelector(".ew-author-validation")')
    checked=g.api('/api/ees-work/workspace?workflow_id='+identifier)['workflow']
    assert checked['validation']['revision']==checked['revision'] and not checked['validation']['errors']
    assert g.browser.evaluate('!document.querySelector(\'[data-author-action="publish"]\').disabled')
    g.capture('figma-b23-publish-review')
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
    g.wait('!!document.querySelector(".ew-adhoc-start")')
    g.type('#ees-work-start [name="evidence_note"]','개발용 시작 근거')
    g.capture('figma-a8-first-start')
    g.click('[data-action="start_run"][data-start-inline]')
    g.wait('!!document.querySelector(\'[data-action="job"]\')')
    state=g.api('/api/ees-work/workspace?workflow_id='+identifier)
    run=state['runs'][0];run_id=run['id']
    assert run['inputs']['evidence_note']=='개발용 시작 근거'
    job_id=next(key for key,node in run['definition']['nodes'].items() if node['type']=='j')
    g.click('[data-action="job"][data-job-id="'+job_id+'"]')
    g.type('#ees-work-inputs [name="evidence_note"]','개발용 합성 근거 v1')
    g.click('[data-action="save_inputs"]')
    g.wait('!document.querySelector(\'[data-action="save_inputs"]\')?.disabled')
    saved=g.api('/api/ees-work/workspace?run_id='+run_id)['run']
    assert saved['inputs']['evidence_note']=='개발용 합성 근거 v1'
    assert saved['jobs'][job_id]['status']!='completed'
    g.capture('a1-input-saved-not-complete')
    q1_native_geometry(g,'figma-q1-1366x768-human-action',require_action=True)
    g.browser.call('Emulation.setDeviceMetricsOverride',{'width':1920,'height':1080,'deviceScaleFactor':1,'mobile':False})
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
    q1_native_geometry(g,'figma-q1-1366x768-native-chat',require_messages=True)
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


def q1_native_geometry(g, name, *, require_action=False, require_messages=False):
    """Read the actual Native layout at the supported 768-pixel height."""
    g.browser.call('Emulation.setDeviceMetricsOverride',{'width':1366,'height':768,'deviceScaleFactor':1,'mobile':False})
    g.wait('document.body.dataset.eesSidebarCompact==="true" && Math.abs(document.querySelector("#sidebar").getBoundingClientRect().width-56)<1')
    stable=g.browser.evaluate('''new Promise(resolve=>{let last='',same=0;const end=performance.now()+3000;
function check(){const elements=['#sidebar','#ees-work-panel','.ees-integrated-chat'].map(s=>document.querySelector(s));
const key=JSON.stringify(elements.map(e=>{const r=e?.getBoundingClientRect();return r?[r.x,r.y,r.width,r.height]:null;}));
same=key===last?same+1:0;last=key;if(same>=3&&elements.every(Boolean))return resolve(true);
if(performance.now()>end)return resolve(false);requestAnimationFrame(check);}check();})''')
    assert stable,'Native layout did not settle after viewport change'
    geometry=g.browser.evaluate('''(()=>{const rect=e=>{if(!e)return null;const r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,bottom:r.bottom,right:r.right};};
return {viewport:[innerWidth,innerHeight],document_width:document.documentElement.scrollWidth,
sidebar:rect(document.querySelector('#sidebar')),panel:rect(document.querySelector('#ees-work-panel')),
chat:rect(document.querySelector('.ees-integrated-chat')),action:rect(document.querySelector('#ees-work-panel>.ew-job-actions')),
messages:[...document.querySelectorAll('.message-listitem')].filter(e=>e.getClientRects().length).map(rect)};})()''')
    (g.out/(name+'-geometry.json')).write_text(json.dumps(geometry,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    assert geometry['document_width']<=1367,geometry
    assert abs(geometry['sidebar']['width']-56)<1,geometry
    assert abs(geometry['panel']['width']-480)<1,geometry
    assert 0<=geometry['panel']['x'] and geometry['panel']['right']<=1367,geometry
    if require_action:
        action=geometry['action'];assert action and action['height']>0 and action['y']>=0 and action['bottom']<=769,geometry
    if require_messages:
        assert geometry['messages'],geometry
        bound=min(760,geometry['chat']['width']-48)
        assert all(item['width']<=bound+1 for item in geometry['messages']),(bound,geometry)
    g.capture(name)
    g.record('Q1 actual Native layout at 1366x768',action_bar_visible=require_action,
        message_width_checked=require_messages,geometry=geometry)


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



def figma_delta_flow(g):
    """Reconstructed actual-product delta gate; all tested actions use real input.

    API writes prepare isolated fixtures only. Native source registration,
    permissions, storage, history and dispatch are the actual packaged product.
    This new source must be rerun; lost prior screenshots are not recreated.
    """
    def command(action, revision=0, **body):
        return g.api('/api/ees-work/workspace/command',
            {'action':action,'expected_revision':revision,'request_id':uuid4().hex,**body})

    def run_state(): return g.api('/api/ees-work/workspace?run_id='+run_id)['run']

    def settle_server(predicate, message):
        deadline=time.monotonic()+15
        while True:
            value=run_state()
            if predicate(value): return value
            assert time.monotonic()<deadline,message
            time.sleep(.05)

    def select_execution_model():
        selector='#ees-work-execution-model';g.wait('!!document.querySelector('+json.dumps(selector)+')')
        index=g.browser.evaluate('[...document.querySelector('+json.dumps(selector)+').options].findIndex(o=>o.value==="c3-synthetic-model")')
        assert index>=0,'Synthetic execution model must be an actual authorized choice'
        g.click(selector)
        for kind in ('keyDown','keyUp'):g.browser.call('Input.dispatchKeyEvent',{'type':kind,'key':'Home','windowsVirtualKeyCode':36})
        for _ in range(index):
            for kind in ('keyDown','keyUp'):g.browser.call('Input.dispatchKeyEvent',{'type':kind,'key':'ArrowDown','windowsVirtualKeyCode':40})
        for kind in ('keyDown','keyUp'):g.browser.call('Input.dispatchKeyEvent',{'type':kind,'key':'Enter','windowsVirtualKeyCode':13})
        g.wait('document.querySelector('+json.dumps(selector)+')?.value==="c3-synthetic-model"')

    def assets(name, expected):
        expression='''(()=>[...document.querySelectorAll('[data-ees-work] img.ew-icon')].filter(e=>e.getClientRects().length).map(e=>{const s=getComputedStyle(e),r=e.getBoundingClientRect();return {file:(e.currentSrc||e.src).split('/').at(-1).split('?')[0],src:e.getAttribute('src'),currentSrc:e.currentSrc,complete:e.complete,loaded:e.complete&&e.naturalWidth>0,natural:[e.naturalWidth,e.naturalHeight],layout:[parseFloat(s.width),parseFloat(s.height)],rect:[r.x,r.y,r.width,r.height],animation:s.animationName};}))()'''
        evidence={'before':g.browser.evaluate(expression),'expected':expected,'scope':'Actual packaged Native product','status':'checking'}
        try:
            g.wait("[...document.querySelectorAll('[data-ees-work] img.ew-icon')].filter(e=>e.getClientRects().length).every(e=>e.complete&&e.naturalWidth>0)")
            observed=g.browser.evaluate(expression)
            for filename,size in expected.items():
                matches=[item for item in observed if item['file']==filename]
                assert matches,('Figma asset slot absent',name,filename)
                assert all(item['loaded'] and item['natural']==[size,size] and item['layout']==[size,size] for item in matches),(name,filename,matches)
            evidence['status']='passed'
        except Exception as error:
            evidence.update(status='failed',error=type(error).__name__+': '+str(error));raise
        finally:
            try:evidence['assets']=g.browser.evaluate(expression)
            except Exception as error:evidence['capture_error']=type(error).__name__+': '+str(error)
            (g.out/(name+'-geometry.json')).write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

    parent_handler=g.provider.server.RequestHandlerClass
    history={'enabled':False,'reference':None,'attempt':None,'question':None,'calls':[],'results':[],'errors':[],'routes':[]}
    config_tree=ast.parse((g.program/'open_webui/config.py').read_text(encoding='utf-8'))
    query_template=next(ast.literal_eval(node.value) for node in config_tree.body if isinstance(node,ast.Assign)
        and any(isinstance(target,ast.Name) and target.id=='DEFAULT_QUERY_GENERATION_PROMPT_TEMPLATE' for target in node.targets))
    assert isinstance(query_template,str) and '{{CURRENT_DATE}}' in query_template and '{{MESSAGES:END:6}}' in query_template
    jira_http=[]

    def save_history_evidence():
        value={key:history[key] for key in ('reference','calls','results','errors','routes')}
        value.update(scope='Actual Native dispatch and storage; synthetic external model',query_template_sha256=hashlib.sha256(query_template.encode()).hexdigest())
        (g.out/'figma-s2-native-historical-tool.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

    def historical_result(value):
        if isinstance(value,str):
            try:return historical_result(json.loads(value))
            except (ValueError,TypeError):return None
        if isinstance(value,dict):
            if value.get('ok') is True and isinstance(value.get('historical'),dict):return value
            for item in value.values():
                if found:=historical_result(item):return found
        if isinstance(value,list):
            for item in value:
                if found:=historical_result(item):return found
        return None

    def historical_reply(payload):
        messages=payload['messages'];prefix=WORK_REFERENCE_PREFIX
        references=[json.JSONDecoder().raw_decode(item['content'][len(prefix):])[0] for item in messages
            if item.get('role')=='system' and isinstance(item.get('content'),str) and item['content'].startswith(prefix)]
        assert references,'Actual Native historical model reference missing'
        observed=references[-1]
        for key in ('workflow_id','run_id','job_id','attempt_id','version','result_revision','context_id'):
            assert observed[key]==history['reference'][key],(key,observed)
        assert observed['reference_kind']=='historical' and observed['read_only'] is True
        last_user=max(i for i,item in enumerate(messages) if item['role']=='user')
        results=[item for item in messages[last_user+1:] if item['role']=='tool']
        if results:
            result=historical_result(results);assert result,('Native historical projection missing',results)
            assert set(result)=={'ok','work_context','historical'}
            attempt=result['historical']['attempt']
            assert attempt['id']==history['attempt']['id'] and attempt['inputs']['project']=='EESEMS'
            assert attempt['result']==history['attempt']['result']
            assert 'AFTER-SYNTHETIC' not in json.dumps(result,ensure_ascii=False)
            history['results'].append(result)
            return {'role':'assistant','content':'당시 조회 근거 EESEMS 확인 완료 · 현재 설정은 사용하지 않았습니다.'},'stop'
        names=[item['function']['name'] for item in payload.get('tools',[]) if item.get('type')=='function']
        names=[name for name in names if name=='ees_workflow_view' or name.endswith('__ees_workflow_view')]
        assert len(names)==1,('Actual registered Native read tool missing',names)
        arguments={'workflow_id':observed['workflow_id'],'run_id':observed['run_id']}
        history['calls'].append({'function':names[0],'reference':observed,'arguments':arguments})
        return {'role':'assistant','content':None,'tool_calls':[{'id':'call_'+uuid4().hex,'type':'function',
            'function':{'name':names[0],'arguments':json.dumps(arguments)}}]},'tool_calls'

    class ReportHandler(parent_handler):
        def do_GET(self):
            fixtures={'/rest/api/2/project':[{'key':'EESEMS','name':'합성 검증 프로젝트'}],
                '/rest/api/2/project/EESEMS/statuses':[{'statuses':[{'id':'1','name':'Open'}]}],
                '/rest/api/2/field':[{'id':'updated','name':'수정일','schema':{'type':'datetime'},'searchable':True}]}
            if self.path in fixtures:return self.answer(fixtures[self.path])
            return super().do_GET()

        def do_POST(self):
            self.report_context=None;self.retrieval_query=False
            if self.path=='/v1/chat/completions':
                raw=self.rfile.read(int(self.headers['Content-Length']));self.rfile=io.BytesIO(raw);payload=json.loads(raw)
                if history['enabled']:
                    route=historical_request_route(payload,history['question'],query_template);history['routes'].append(route)
                    if route['kind']=='native_retrieval_query':
                        self.retrieval_query=True;route['synthetic_queries']=['EESEMS 합성 첨부 검증'];save_history_evidence()
                        return super().do_POST()
                    try:
                        assert route['kind']=='historical_main',('Unclassified Native model request',route)
                        message,reason=historical_reply(payload)
                    except Exception as error:
                        history['errors'].append(type(error).__name__+': '+str(error));save_history_evidence()
                        return self.answer({'error':'Synthetic historical model contract assertion failed'},500)
                    save_history_evidence();identifier='historical-'+uuid4().hex
                    if payload.get('stream'):
                        self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Cache-Control','no-cache');self.end_headers()
                        if message.get('tool_calls'):message['tool_calls']=[{'index':i,**item} for i,item in enumerate(message['tool_calls'])]
                        for delta,finish in ((message,None),({},reason)):
                            chunk={'id':identifier,'object':'chat.completion.chunk','created':int(time.time()),'model':payload['model'],
                                'choices':[{'index':0,'delta':delta,'finish_reason':finish}]}
                            self.wfile.write(('data: '+json.dumps(chunk,ensure_ascii=False)+'\n\n').encode());self.wfile.flush()
                        self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush();return
                    return self.answer({'id':identifier,'object':'chat.completion','created':int(time.time()),'model':payload['model'],
                        'choices':[{'index':0,'message':message,'finish_reason':reason}],'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}})
                text=next((item.get('content') for item in reversed(payload.get('messages',[])) if item.get('role')=='user'),'')
                try:context=json.loads(text).get('context')
                except (ValueError,TypeError,AttributeError):context=None
                if isinstance(context,dict) and context.get('kind')=='report':self.report_context=context
            return super().do_POST()

        def answer(self,value,code=200):
            if self.path.startswith('/rest/api/'):
                jira_http.append({'path':self.path.split('?')[0],'status':code})
                if isinstance(value,dict) and isinstance(value.get('issues'),list):
                    for issue in value['issues']:
                        issue['fields']['status']['id']='1';issue['fields']['attachment']=[]
            if isinstance(value,dict) and value.get('object')=='chat.completion':
                if getattr(self,'retrieval_query',False):value['choices'][0]['message']['content']=json.dumps({'queries':['EESEMS 합성 첨부 검증']},ensure_ascii=False)
                if getattr(self,'report_context',None):value['choices'][0]['message']['content']=json.dumps({'context':self.report_context,'proposal':'합성 AI 검토 원문: 실제 송부하지 않은 결과 초안입니다.'},ensure_ascii=False)
            return super().answer(value,code)

    g.provider.server.RequestHandlerClass=ReportHandler
    g.browser.call('Emulation.setDeviceMetricsOverride',{'width':1920,'height':1080,'deviceScaleFactor':1,'mobile':False})
    g.browser.call('Emulation.setEmulatedMedia',{'features':[{'name':'prefers-reduced-motion','value':'no-preference'}]})
    g.navigate('/');g.wait_work_ready();g.click('[data-action="my_work"]')
    g.wait_work_ready(selector='.ew-my-work-empty');assets('figma-s1-empty',{'52271.svg':16});g.capture('figma-s1-empty')
    tool='integrated_figma_jira'
    source=(Path(__file__).resolve().parents[1]/'agent-pack/skills/jira-read/scripts/jira_tool.py').read_text(encoding='utf-8')
    g.api('/api/v1/tools/create',{'id':tool,'name':'합성 Figma 검수 Jira','content':source,'meta':{'description':'Isolated loopback verification only'},'access_grants':[]})
    g.api('/api/v1/tools/id/'+tool+'/valves/update',{'ENABLED':True,'ALLOW_HTTP':True,'JIRA_BASE_URL':g.provider.base,'ALLOWED_PROJECTS':'EESEMS','TIMEOUT_SECONDS':30})
    g.api('/api/v1/tools/id/'+tool+'/valves/user/update',{'PAT':'synthetic-local-figma'})
    inspected=g.api('/api/ees-work/execution/capability?tool_id='+tool+'&function=jira_search_crs')['capability']
    reference=g.api('/api/ees-work/execution/capability/action',{'action':'approve','reference':inspected['reference'],
        'evidence':'Actual Native connector; isolated loopback synthetic Jira'})['capability']['reference']
    actor=g.api('/api/v1/auths/')['id'];status=g.api('/api/v1/ees/assets/work-tool/status')
    assert status['source_sha256']==hashlib.sha256((g.program/'open_webui/ees_workflow_tool.py').read_bytes()).hexdigest()
    setup=g.api('/api/v1/ees/assets/work-tool/setup',{'source_sha256':status['source_sha256'],'expected_token':status['expected_token'],
        'confirmation':'register_readonly_work_tool','access_grants':[{'principal_type':'user','principal_id':actor,'permission':'read'}]})
    assert setup['state']=='ready'
    made=command('create_workflow',name='합성 변경 화면 검수',system_id='EMS',mode='on_demand')
    workflow_id=made['workflow_id'];definition=made['workflow']['draft'];root=next(iter(definition['nodes']))
    anchor=(datetime.now(timezone.utc)+timedelta(days=2)).replace(hour=9,minute=0,second=0,microsecond=0,tzinfo=None).isoformat(timespec='minutes')
    definition['schedule']={'frequency':'daily','interval':1,'timezone':'UTC','anchor':anchor,'name_template':'{date} 합성 회차',
        'opening':'after_previous_closed','closing':'after_last_stage','non_working_days':'notify_no_shift',
        'stage_deadlines':{'qa-stage':{'offset_days':-1}},'catch_up':'miss'}
    definition['nodes'][root]['children']=['qa-stage']
    definition['nodes']['qa-stage']={'id':'qa-stage','type':'t','name':'합성 조회와 검토','parent':root,'children':['qa-list','qa-report'],'deps':[]}
    definition['nodes']['qa-list']={'id':'qa-list','type':'j','name':'합성 Jira 목록 확정','parent':'qa-stage','children':[],'deps':[],
        'mode':'tool','result_block':'list_confirm','human_confirmation':True,'read_retry':{'count':1,'deadline_seconds':30},
        'inputs':[{'id':'project','name':'조회 프로젝트','type':'text','scope':'workflow','required':True}],
        'tool_reference':reference,'argument_bindings':{'project_key':{'input':'project'},'status_ids':{'constant':['1']},
            'date_field':{'constant':'updated'},'start_date':{'constant':'2026-09-01'},'end_date':{'constant':'2026-09-30'},'start_at':{'constant':0}},
        'instructions':'실제 Native 등록 도구로 합성 Jira 목록을 조회합니다.'}
    definition['nodes']['qa-report']={'id':'qa-report','type':'j','name':'합성 결과 초안 검토','parent':'qa-stage','children':[],'deps':['qa-list'],
        'mode':'ai','result_block':'ai_review','human_confirmation':True,'inputs':[],'completion':{'kind':'review'},
        'instructions':'확정 목록을 바탕으로 검토 초안을 작성합니다. 실제 송부하지 않습니다.'}
    command('save_draft',1,workflow_id=workflow_id,definition=definition)
    assert command('validate_workflow',2,workflow_id=workflow_id)['validation']['errors']==[]
    command('publish_workflow',2,workflow_id=workflow_id);command('save_settings',workflow_id=workflow_id,values={'project':'EESEMS'})
    g.record('latest Figma isolated API fixtures',workflow_id=workflow_id,native_tool_source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        business_completion=False,external_boundary='Loopback synthetic Jira and model HTTP only')

    # Isolated unpublished checklist fixture makes B2-2 meaningful without
    # changing the existing human_confirm contract exercised above.
    rule_fixture=command('create_workflow',name='합성 작업별 판정 지침',system_id='EMS',mode='on_demand')
    rule_id=rule_fixture['workflow_id'];rule_definition=rule_fixture['workflow']['draft']
    rule_root=next(iter(rule_definition['nodes']))
    rule_definition['nodes'][rule_root]['children']=['rule-stage']
    rule_definition['nodes']['rule-stage']={'id':'rule-stage','type':'t','name':'근거 확인',
        'parent':rule_root,'children':['rule-checklist'],'deps':[]}
    rule_definition['nodes']['rule-checklist']={'id':'rule-checklist','type':'j','name':'사람이 확정하는 확인 항목',
        'parent':'rule-stage','children':[],'deps':[],'mode':'human','result_block':'checklist',
        'inputs':[],'instructions':'합성 확인 항목의 근거를 사람이 확인합니다.'}
    command('save_draft',1,workflow_id=rule_id,definition=rule_definition)
    g.navigate('/');g.wait_work_ready()
    g.click('[data-action="mode"][data-mode="author"]');g.click('[data-action="procedures"]')
    g.click('[data-author-action="open"][data-id="'+rule_id+'"]')
    g.click('[data-author-action="tab"][data-tab="rules"]')
    g.wait('document.querySelector(\'select[name="rule_job_id"]\')?.value==="rule-checklist"')
    assert g.browser.evaluate('document.querySelectorAll(".ew-author-rule-card tbody tr").length>0')
    guidance='합성 근거만 제안에 사용하며 사람의 판정을 대신하지 않습니다.'
    g.type('#ew-author-rules [name="suggestion_description"]',guidance)
    g.click('[data-author-action="save"]')
    g.wait('!document.querySelector(\'[data-author-action="validate"]\')?.disabled')
    saved_rules=g.api('/api/ees-work/workspace?workflow_id='+rule_id)['workflow']
    assert saved_rules['draft']['nodes']['rule-checklist']['suggestion_rules']['description']==guidance
    assert not saved_rules['published_version']
    assert not any(run['workflow_id']==rule_id for run in g.api('/api/ees-work/workspace?workflow_id='+rule_id)['runs'])
    g.capture('figma-b22-saved-job-rules')
    g.record('Figma B2-2 physical job rule edit and draft save',workflow_id=rule_id,
        result_block='checklist',published=False,business_completion=False)

    # Procedure navigation is rendered only inside the actual workspace mode.
    g.click('[data-action="mode"][data-mode="author"]')
    g.wait('document.querySelector(\'[data-action="mode"][data-mode="author"]\')?.getAttribute("aria-pressed")==="true"')
    g.click('[data-action="procedures"]')
    g.click('[data-author-action="open"][data-id="'+workflow_id+'"]')
    g.click('[data-author-action="tab"][data-tab="schedule"]')
    g.click('[data-author-action="run_mode"][data-id="periodic"]')
    g.select('#ew-author-schedule [name="opening"]','on_schedule')
    g.type('#ew-author-schedule [name="interval"]','2')
    g.type('#ew-author-schedule [name="name_template"]','{date} 실제 검수 회차')
    g.click('[data-author-action="schedule_preview"]')
    g.wait('document.querySelector(".ew-schedule-preview")?.innerText.includes("그다음")')
    assets('figma-b21-schedule',{'ead50.svg':14,'1fc4e.svg':14});g.capture('figma-b21-schedule-preview')
    g.click('[data-author-action="save"]');g.wait('!document.querySelector(\'[data-author-action="save"]\')?.disabled')
    saved=g.api('/api/ees-work/workspace?workflow_id='+workflow_id)['workflow']
    assert saved['draft']['mode']=='periodic' and saved['draft']['schedule']['interval']==2
    assert saved['draft']['schedule']['name_template']=='{date} 실제 검수 회차'
    assert saved['draft']['schedule']['opening']=='on_schedule'
    assert saved['published_version']==1 and saved['published']['mode']=='on_demand'
    assert saved['published']['schedule']['opening']=='after_previous_closed','An old immutable publication must retain its snapshot'
    assert not g.api('/api/ees-work/operations?system_id=EMS')['schedules']
    g.record('Figma B2-1 physical schedule preview and draft save',draft_revision=saved['revision'],published_version=1,reservation_created=False)
    g.click('[data-action="mode"][data-mode="work"]');g.click('[data-action="workflow"][data-workflow-id="'+workflow_id+'"]')
    g.click('[data-action="start_run"][data-start-inline]')
    g.wait('!!document.querySelector(\'[data-action="job"][data-job-id="qa-list"]\')')
    run_id=g.api('/api/ees-work/workspace?workflow_id='+workflow_id)['runs'][0]['id']
    g.wait_work_ready(workflow_id=workflow_id,run_id=run_id)
    assets('figma-a5-cycle',{'a28e3.svg':13,'b22ad.svg':13,'69549.svg':14});g.capture('figma-a5-cycle-overview')
    g.click('[data-action="job"][data-job-id="qa-list"]');g.wait_work_ready(run_id=run_id,selector='[data-action="execute"]')
    g.provider.fail_next=True;http_start=len(jira_http);g.click('[data-action="execute"]')
    retried=settle_server(lambda value:len([a for a in value['attempts'] if a['job_id']=='qa-list'])==2
        and value['jobs']['qa-list']['status']!='running','Actual bounded read retry did not finish')
    retry_http=jira_http[http_start:]
    (g.out/'figma-s1-read-retry-server.json').write_text(json.dumps({'run':retried,'http':retry_http,'scope':'Synthetic actual Native connector HTTP'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    failed,original=[a for a in retried['attempts'] if a['job_id']=='qa-list']
    assert failed['status']=='failed' and original['status']=='succeeded'
    assert failed['result']['error']['code']=='upstream_error' and failed['result']['failure_confirmed'] is True
    assert retry_http==[
        {'path':'/rest/api/2/myself','status':503},
        {'path':'/rest/api/2/myself','status':200},
        {'path':'/rest/api/2/project','status':200},
        {'path':'/rest/api/2/project/EESEMS/statuses','status':200},
        {'path':'/rest/api/2/field','status':200},
        {'path':'/rest/api/2/search','status':200}],retry_http
    assert original['inputs']['project']=='EESEMS' and len(original['result']['items'])==1
    assert retried['jobs']['qa-list']['status']=='waiting_confirmation' and not retried['jobs']['qa-list']['decisions']
    g.wait_work_ready(run_id=run_id,selector='.ew-list-confirm');g.wait('!!document.querySelector(\'[data-item-id="EESEMS-1"]\')')
    g.capture('figma-s1-read-retry-awaits-human')
    g.record('Figma S1 actual HTTP failure and bounded read retry',attempt_statuses=['failed','succeeded'],external_http_requests=retry_http,
        native_tool_attempts=2,business_completed=False,failed_result_preserved=True)
    g.click('[data-item-id="EESEMS-1"]');assert len(run_state()['attempts'])==2
    g.click('[data-item-id="EESEMS-1"]')
    g.click('[data-action="add_list_item"]');g.type('#ees-list-add-id','SYNTHETIC-MANUAL-2');g.type('#ees-list-add-name','합성 수동 검토 항목')
    g.click('#ees-work-dialog [data-dialog-confirm]');assert len(run_state()['attempts'])==2
    assets('figma-a6-list',{'f1e53.svg':13,'b456d.svg':13});g.capture('figma-a6-list-local-selection')
    g.click('[data-action="confirm_list"]');g.wait("document.activeElement?.matches('#ees-work-dialog [data-dialog-cancel]')")
    g.type('#ees-list-confirm-reason','합성 검토자가 원본 목록과 추가 항목을 확인했습니다.');g.click('#ees-work-dialog [data-dialog-confirm]')
    g.wait('document.querySelector(".ew-list-confirm")?.innerText.includes("사람 확정 기록 있음")')
    confirmed=run_state();assert confirmed['jobs']['qa-list']['status']=='completed'
    assert confirmed['attempts'][0]==failed and confirmed['attempts'][1]['result']==original['result'] and len(confirmed['attempts'])==3
    assert {item['item_id'] for item in confirmed['jobs']['qa-list']['decisions']}=={'EESEMS-1','SYNTHETIC-MANUAL-2'}
    g.wait_work_ready(run_id=run_id);g.capture('figma-a6-list-confirmed')
    g.record('Figma A6 physical Native tool call list selection and atomic confirmation',attempts=3,original_result_preserved=True,confirmed_items=2)

    g.click('[data-action="overview"]');g.click('[data-action="job"][data-job-id="qa-report"]')
    select_execution_model();g.click('[data-action="execute"]')
    g.wait('document.querySelector("#ees-review-text")?.value.includes("합성 AI 검토 원문")',20000)
    original_report=next(item for item in run_state()['attempts'] if item['job_id']=='qa-report')['result']
    text='사람이 보완한 실제 제품 검토 본문. 합성 자료이며 송부하지 않았습니다.';g.type('#ees-review-text',text)
    edited=settle_server(lambda value:(value['jobs']['qa-report'].get('review_draft') or {}).get('text')==text,
        'Physical review edit was not autosaved by actual server')
    # Server acceptance does not imply that the refreshed panel has settled.
    g.wait_work_ready(workflow_id=workflow_id,run_id=run_id,selector='#ees-review-text')
    draft_revision=edited['jobs']['qa-report']['review_draft']['revision']
    g.wait('document.querySelector("#ees-review-text")?.value==='+json.dumps(text)+
        '&&document.querySelector("#ees-review-text")?.dataset.reviewRevision==='+json.dumps(str(draft_revision))+
        '&&document.activeElement?.id==="ees-review-text"')
    assert edited['jobs']['qa-report']['decisions']==[]
    assert next(item for item in edited['attempts'] if item['job_id']=='qa-report')['result']==original_report
    assert edited['definition']['nodes']['qa-report']['completion']['kind']=='review' and original_report['sent'] is False
    assert g.browser.evaluate('!document.querySelector(\'[data-action="send_review_draft"]\')')
    assert g.browser.evaluate('!document.querySelector(\'[data-action="save_review_draft"]\')'),'A7 draft must autosave without a save button'
    assets('figma-a7-review',{'b22ad.svg':13});g.capture('figma-a7-review-only-autosaved')
    g.click('[data-action="confirm"]');g.click('#ees-work-dialog [data-dialog-confirm]')
    final=settle_server(lambda value:value['jobs']['qa-report']['status']=='completed','Review confirmation missing')
    g.wait('document.querySelector("#ees-review-text")?.readOnly&&!document.querySelector(\'[data-action="save_review_draft"]\')')
    g.wait_work_ready(run_id=run_id,selector='#ees-review-text')
    confirmed_report=next(item for item in final['attempts'] if item['job_id']=='qa-report')
    assert confirmed_report['review_history'][-1]['text']==text and confirmed_report['review_history'][-1]['decision_id']
    assert confirmed_report['result']==original_report and confirmed_report['result']['sent'] is False
    assert g.browser.evaluate('!document.querySelector(\'[data-action="send_review_draft"]\')')
    g.capture('figma-a7-confirmed-readonly')
    g.record('Figma A7 physical AI review autosave and explicit confirmation',completion_kind='review',actual_delivery=False,
        original_result_preserved=True,autosave_confirmed=False,send_control_present=False,confirmed_text=text)

    g.click('[data-action="overview"]');g.click('[data-action="close_run"]');g.click('#ees-work-dialog [data-dialog-confirm]')
    closed=settle_server(lambda value:value['status']=='completed','Run closure missing')
    command('save_settings',1,workflow_id=workflow_id,values={'project':'AFTER-SYNTHETIC'})
    history_chat_id=next(item['chat_id'] for item in g.report['steps'] if item['name']=='Native physical send and storage reload')
    previous_chat=g.api('/api/v1/chats/'+history_chat_id)['chat'];expected_messages=len(previous_chat['history']['messages'])+2
    g.navigate('/c/'+history_chat_id);g.wait_work_ready();g.click('[data-action="records"]')
    g.click('[data-action="open_run"][data-run-id="'+run_id+'"]');g.click('[data-action="workflow_records"]')
    g.wait_work_ready();assets('figma-s2-filter',{'6d84b.svg':11});g.capture('figma-s2-filtered-records')
    g.click('[data-action="open_run"][data-run-id="'+run_id+'"]')
    historical_selector='.ew-history[data-key="history-'+original['id']+'"]'
    g.wait_work_ready(run_id=run_id,selector=historical_selector+' summary');g.click(historical_selector+' summary')
    historical_values=json.dumps(historical_selector+'[open] .ew-history-values')
    g.wait('document.querySelector('+historical_values+')?.innerText.includes("EESEMS")')
    assert g.browser.evaluate('document.querySelector('+historical_values+')?.innerText.includes("지금과 다름")')
    assets('figma-s2-history',{'1c98e.svg':14});g.capture('figma-s2-readonly-original-values')
    before=run_state();g.click('[data-action="ask_record"][data-attempt-id="'+original['id']+'"]')
    assert run_state()['attempts']==before['attempts'] and run_state()['revision']==before['revision']
    mutation_selector='#ees-work-panel [data-action="execute"],#ees-work-panel [data-action="confirm"],#ees-work-panel [data-action="save_inputs"]'
    assert g.browser.evaluate('!document.querySelector('+json.dumps(mutation_selector)+')')
    history['reference']=g.browser.evaluate('window.__eesNativeWorkV1.captureReference()')
    assert history['reference']['attempt_id']==original['id'] and history['reference']['reference_kind']=='historical'
    question='이 당시 조회 시도의 프로젝트와 결과만 설명해 줘. 현재 값이나 다른 시도는 사용하지 마.'
    history['attempt']=original;history['question']=question;history['enabled']=True
    g.type('#chat-input',question);g.click('#send-message-button')
    g.wait('document.querySelector("#chat-container")?.innerText.includes("당시 조회 근거 EESEMS 확인 완료")',20000)
    chat=g.completed_chat(history_chat_id,expected_messages);history['enabled']=False;save_history_evidence()
    assert not history['errors'] and len(history['calls'])==1 and len(history['results'])==1,history
    message=next(item for item in chat['history']['messages'].values() if item.get('role')=='user' and item.get('content')==question)
    assert message['meta']['ees_work_reference']['attempt_id']==original['id']
    assert run_state()['attempts']==before['attempts'] and run_state()['revision']==before['revision']
    g.wait_work_ready(workflow_id=workflow_id,run_id=run_id,attempt_id=original['id']);g.capture('figma-s2-native-historical-answer')
    g.navigate('/c/'+history_chat_id)
    g.wait('document.querySelector("#chat-container")?.innerText.includes("당시 조회 근거 EESEMS 확인 완료")')
    # This was missing from the lost gate: chat render and font readiness can
    # coexist with Work's loading screen. Require the exact restored reference.
    restored=g.wait_work_ready(workflow_id=workflow_id,run_id=run_id,attempt_id=original['id'],selector=historical_selector+' summary')
    assert g.api('/api/v1/chats/'+history_chat_id)['chat']['history']==chat['history']
    if not g.browser.evaluate('document.querySelector('+json.dumps(historical_selector)+')?.open'):
        g.click(historical_selector+' summary')
    g.browser.call('Emulation.setDeviceMetricsOverride',{'width':1100,'height':800,'deviceScaleFactor':1,'mobile':False})
    g.wait('innerWidth===1100&&innerHeight===800')
    g.wait_work_ready(workflow_id=workflow_id,run_id=run_id,attempt_id=original['id'],selector=historical_selector+'[open] .ew-history-values')
    g.wait('document.querySelector('+historical_values+')?.innerText.includes("EESEMS")')
    assert g.browser.evaluate('document.querySelector('+historical_values+')?.innerText.includes("지금과 다름")')
    assert g.browser.evaluate('!document.querySelector('+json.dumps(mutation_selector)+')')
    assert g.browser.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    scroll_expression='''(()=>{const e=document.querySelector('#ees-work-content'),r=e.getBoundingClientRect();return {top:e.scrollTop,height:e.clientHeight,total:e.scrollHeight,width:e.clientWidth,total_width:e.scrollWidth,x:r.x+6,y:r.y+r.height/2,open:document.querySelector(HISTORY)?.open};})()'''.replace('HISTORY',json.dumps(historical_selector))
    scroll_before=g.browser.evaluate(scroll_expression)
    assert scroll_before['open'] and scroll_before['total']>scroll_before['height']
    assert scroll_before['total_width']<=scroll_before['width']+1
    g.capture('figma-s2-narrow-readonly-before-scroll')
    delta=-180 if scroll_before['top']>50 else 180
    g.browser.call('Input.dispatchMouseEvent',{'type':'mouseWheel','x':scroll_before['x'],'y':scroll_before['y'],'deltaX':0,'deltaY':delta})
    g.wait('Math.abs(document.querySelector("#ees-work-content").scrollTop-'+str(scroll_before['top'])+')>1')
    scroll_after=g.browser.evaluate(scroll_expression)
    g.wait_work_ready(workflow_id=workflow_id,run_id=run_id,attempt_id=original['id'],selector=historical_selector+'[open] .ew-history-values')
    assert g.browser.evaluate('!document.querySelector('+json.dumps(mutation_selector)+')')
    assert run_state()['attempts']==before['attempts'] and run_state()['revision']==before['revision']
    (g.out/'figma-s2-restored-narrow-scroll.json').write_text(json.dumps({'restored':restored,'before':scroll_before,'after':scroll_after,
        'physical_input':'CDP mouseWheel','readonly_controls_absent':True,'run_revision_unchanged':True,
        'note':'Document/font readiness alone is not Work restoration evidence.'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    g.capture('figma-s2-narrow-scroll');g.stop_server();g.launch()
    assert run_state()['attempts']==closed['attempts']
    g.record('Figma S2 physical readonly history and reference with restart persistence',original_shared_value_preserved=True,
        current_value_not_substituted=True,attempts=len(closed['attempts']),actual_native_historical_tool_calls=1,
        stored_chat_messages=expected_messages,narrow_work_ready=True,physical_scroll_verified=True)

    factory_id='synthetic-c12-factory'
    command('save_factory',factory_id=factory_id,system_id='EMS',name='합성 C12 검수 공장',attributes={})
    made=command('create_workflow',name='합성 실제 송부 차단 검수',system_id='EMS',mode='on_demand')
    delivery_id=made['workflow_id'];delivery=made['workflow']['draft'];delivery_root=next(iter(delivery['nodes']))
    delivery['execution_scope']='factory'
    delivery['nodes'][delivery_root]['children']=['delivery-stage']
    delivery['nodes']['delivery-stage']={'id':'delivery-stage','type':'t','name':'송부 검토','parent':delivery_root,'children':['delivery-report'],'deps':[]}
    delivery['nodes']['delivery-report']={'id':'delivery-report','type':'j','name':'실제 송부 목적 초안','parent':'delivery-stage','children':[],'deps':[],
        'mode':'ai','result_block':'ai_review','human_confirmation':True,'inputs':[],'completion':{'kind':'delivery'},'instructions':'합성 송부 검토만 수행합니다.'}
    command('save_draft',1,workflow_id=delivery_id,definition=delivery)
    g.browser.call('Emulation.setDeviceMetricsOverride',{'width':1920,'height':1080,'deviceScaleFactor':1,'mobile':False})
    g.navigate('/');g.wait_work_ready();g.click('[data-action="mode"][data-mode="author"]')
    g.click('[data-action="procedures"]');g.click('[data-author-action="open"][data-id="'+delivery_id+'"]')
    g.click('[data-author-action="validate"]');g.wait('!!document.querySelector(".ew-author-validation")')
    advisory=g.api('/api/ees-work/workspace?workflow_id='+delivery_id)['workflow']['validation']
    assert not advisory['errors'] and any('송부 방식' in str(item) for item in advisory['warnings']),advisory
    # The validation panel can render while its follow-up workspace read is
    # still pending. Require the physical publish action to be ready before
    # assessing advisory-only publication; never enable it from the fixture.
    g.wait('document.querySelector(\'[data-author-action="publish"]\')?.disabled === false')
    assert g.browser.evaluate('!document.querySelector(\'[data-author-action="publish"]\').disabled')
    g.capture('figma-b23-delivery-advisory-publish-enabled')
    g.click('[data-author-action="publish"]');g.click('#ees-work-dialog [data-dialog-confirm]')
    g.wait('document.querySelector("#ees-work-designer")?.innerText.includes("게시 v1")')
    assert g.api('/api/ees-work/workspace?workflow_id='+delivery_id)['workflow']['published_version']==1
    g.record('Figma B2-3 delivery recommendation permits physical publish',recommendations=len(advisory['warnings']),external_delivery=False)
    g.click('[data-action="mode"][data-mode="work"]');g.click('[data-action="workflow"][data-workflow-id="'+delivery_id+'"]')
    g.select('#ees-start-factory',factory_id)
    g.capture('figma-a8-factory-ready')
    g.click('[data-action="start_run"][data-start-inline]')
    g.click('[data-action="job"][data-job-id="delivery-report"]');select_execution_model();g.click('[data-action="execute"]')
    g.wait('document.querySelector("#ees-review-text")?.value.includes("합성 AI 검토 원문")',20000)
    delivery_run_id=g.api('/api/ees-work/workspace?workflow_id='+delivery_id)['runs'][0]['id']
    g.click('[data-action="confirm"]');g.click('#ees-work-dialog [data-dialog-confirm]')
    g.wait('document.querySelector("#ees-work-panel")?.innerText.includes("실제 송부와 결과 확인 전")')
    g.wait_work_ready(workflow_id=delivery_id,run_id=delivery_run_id,selector='#ees-review-text')
    blocked=g.api('/api/ees-work/workspace?run_id='+delivery_run_id)['run']
    assert blocked['status']=='open' and blocked['jobs']['delivery-report']['status']=='blocked'
    assert blocked['jobs']['delivery-report']['reason']=='delivery_unconfigured'
    delivery_attempt=next(item for item in blocked['attempts'] if item['job_id']=='delivery-report')
    assert delivery_attempt['result']['sent'] is False and delivery_attempt['review_history'][-1]['decision_id']
    assert g.browser.evaluate('document.querySelector(\'[data-action="send_review_draft"]\')?.disabled')
    g.capture('figma-a7-delivery-reviewed-still-blocked')
    g.click('[data-action="overview"]');g.click('[data-action="close_run"]');g.click('#ees-work-dialog [data-dialog-confirm]')
    g.wait('document.querySelector("#ees-work-panel")?.innerText.includes("필수 작업의 판정")')
    assert g.api('/api/ees-work/workspace?run_id='+delivery_run_id)['run']==blocked
    g.record('Figma A7 delivery purpose review cannot close or claim sent',completion_kind='delivery',human_review_saved=True,
        business_status='blocked',reason='delivery_unconfigured',actual_delivery=False)
    assert blocked['factory_id']==factory_id
    g.click('[data-action="workflow"][data-workflow-id="'+delivery_id+'"]')
    g.wait('!!document.querySelector(".ew-active-runs")')
    assert g.browser.evaluate('document.querySelector(\'#ees-start-factory option[value="'+factory_id+'"]\')?.disabled')
    assert g.browser.evaluate('document.querySelector(\'.ew-active-runs [data-run-id="'+delivery_run_id+'"]\')?.getClientRects().length>0')
    assert g.browser.evaluate('document.querySelector(\'[data-action="start_run"][data-start-inline]\')?.disabled')
    assert g.api('/api/ees-work/workspace?run_id='+delivery_run_id)['run']==blocked
    g.capture('figma-a8-active-factory-duplicate-disabled')
    g.record('Figma A8 active factory remains visible and duplicate start is disabled',factory_id=factory_id,
        existing_run_unchanged=True,duplicate_created=False)


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
