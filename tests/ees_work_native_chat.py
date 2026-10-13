"""Actual packaged Native central chat, human drafts and isolated helper replies.

Only the OpenAI HTTP model is synthetic. Native tool registration/loading,
current identity/ACL, chat persistence, event bridge and EES SQLite are actual
product code. A model proposal must not save, publish, execute or confirm work.
Helper sends read shipped help only, preserve composer/chat state and fail before
message persistence/model dispatch when current tool/model access is missing.
"""
import argparse
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import hashlib
from pathlib import Path
import threading
import time
from unittest.mock import patch
from uuid import uuid4
from urllib.parse import urlencode

import ees_work_integrated_app as integrated


class NativeChatGate(integrated.ProductGate):
    def native_socket_ready(self):
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            self.browser.evaluate('document.readyState')
            if any(event.get('method')=='Network.webSocketFrameSent' and '"user-join"' in event.get('params',{}).get('response',{}).get('payloadData','') for event in self.browser.events):
                self.record('actual Native authenticated socket join sent',credential_payload_recorded=False)
                self.browser.call('Page.bringToFront');return
            time.sleep(.05)
        raise AssertionError('Native authenticated socket join was not observed before central chat')


class NativeToolProvider:
    """A deterministic external model, never a replacement EES executor."""
    def __init__(self):
        self.calls=[];self.models=[];self.errors=[];self.tool_results=[]
        self.mode='plain';self.reference=None;self.definition=None;self.proposed=None
        self.plain_reply='중앙 대화의 합성 연결 준비 완료';self.input_proposals=[]
        self.helper_payloads=[];self.helper_results=[];self.helper_question=''
        self.helper_workflow='';self.helper_reply='업무 도우미가 실제 등록된 읽기 도구로 안내했습니다.'
        self.allow_embeddings=True
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def answer(self,value,status=200):
                data=json.dumps(value,ensure_ascii=False).encode()
                self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers()
                self.wfile.write(data)
            def do_GET(self):
                if self.path=='/v1/models':return self.answer({'object':'list','data':[{'id':'c3-synthetic-model','object':'model','created':1,'owned_by':'openai'}]})
                return self.answer({'error':'Unexpected synthetic route'},404)
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if self.path=='/v1/embeddings':
                    values=body.get('input',[]);values=[values] if isinstance(values,str) else values
                    return self.answer({'object':'list','data':[{'object':'embedding','index':i,'embedding':[1.,.5,.25]} for i,_ in enumerate(values)],'model':body.get('model'),'usage':{'prompt_tokens':1,'total_tokens':1}})
                if self.path!='/v1/chat/completions':return self.answer({'error':'Unexpected synthetic route'},404)
                try:message,reason=owner.reply(body)
                except Exception as error:
                    owner.errors.append(type(error).__name__+': '+str(error));return self.answer({'error':'Synthetic model contract assertion failed'},500)
                identifier='native-work-'+uuid4().hex
                if body.get('stream'):
                    self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Cache-Control','no-cache');self.end_headers()
                    delta=deepcopy(message)
                    if delta.get('tool_calls'):
                        delta['tool_calls']=[{'index':i,**item} for i,item in enumerate(delta['tool_calls'])]
                    for value,finish in ((delta,None),({},reason)):
                        chunk={'id':identifier,'object':'chat.completion.chunk','created':int(time.time()),'model':body['model'],'choices':[{'index':0,'delta':value,'finish_reason':finish}]}
                        self.wfile.write(('data: '+json.dumps(chunk,ensure_ascii=False)+'\n\n').encode());self.wfile.flush()
                    self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush();return
                return self.answer({'id':identifier,'object':'chat.completion','created':int(time.time()),'model':body['model'],'choices':[{'index':0,'message':message,'finish_reason':reason}],'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}})
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.daemon_threads=True
        self.base='http://127.0.0.1:'+str(self.server.server_port)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    def reply(self,body):
        messages=body['messages'];tools=body.get('tools',[])
        names=[tool['function']['name'] for tool in tools if tool.get('type')=='function']
        self.models.append({'mode':self.mode,'advertised_tool_names':names,'stream':bool(body.get('stream')),'roles':[message['role'] for message in messages]})
        # The product's separate unsaved-input proposal path sends its exact
        # scoped context as JSON and explicitly prohibits tool execution.
        if not body.get('stream') and not names:
            try:scoped=json.loads(messages[-1].get('content',''))
            except (ValueError,TypeError):scoped={}
            if scoped.get('context',{}).get('kind')=='inputs':
                assert not tools and not body.get('tool_ids')
                fields=scoped['untrusted_source']['fields'];assert [field['id'] for field in fields]==['note']
                self.input_proposals.append(deepcopy(scoped))
                return {'role':'assistant','content':json.dumps({'context':scoped['context'],'proposal':{'note':'AI가 제안한 첫 입력'}},ensure_ascii=False)},'stop'
        if self.mode=='plain':return {'role':'assistant','content':self.plain_reply},'stop'
        if self.mode=='help':return self.reply_help(body,names)
        last_user=max(i for i,message in enumerate(messages) if message['role']=='user')
        results=[message for message in messages[last_user+1:] if message['role']=='tool']
        if results:
            self.tool_results.extend(deepcopy(results))
            if self.mode=='read':
                parsed=self.find_workflow(results)
                assert parsed and parsed['id']==self.reference['workflow_id'],'Native read tool did not return the actual authorized procedure'
                self.definition=deepcopy(parsed['draft']);assert parsed['revision']==self.reference['revision']
            else:
                proposal=self.find_proposal(results)
                assert proposal and proposal.get('ok') is True and proposal.get('proposal',{}).get('ok') is True,('Actual Native proposal did not reach the current editor',results)
            return {'role':'assistant','content':'중앙 도구 조회 완료' if self.mode=='read' else '중앙 제안은 검토 전이며 저장하지 않았습니다'},'stop'
        expected='ees_workflow_view' if self.mode=='read' else 'ees_workflow_propose'
        candidates=[name for name in names if name==expected or name.endswith('__'+expected)]
        assert len(candidates)==1,(expected,names)
        assert not any(name.startswith('ees_') and any(verb in name for verb in ('execute','publish','confirm','approve','save')) for name in names),names
        references=[]
        prefix='EES Work context (read-only reference): '
        for item in messages:
            content=item.get('content')
            if isinstance(content,str) and content.startswith(prefix):
                references.append(json.JSONDecoder().raw_decode(content[len(prefix):])[0])
        # Compare a reference actually delivered by Native middleware. Merely
        # handing expected values to this synthetic model cannot satisfy this.
        assert references and references[-1]['workflow_id']==self.reference['workflow_id'] and references[-1]['context_id']==self.reference['context_id'] and references[-1]['revision']==self.reference['revision'],'Current Work reference absent or stale in actual model context'
        if self.mode=='read':arguments={'workflow_id':self.reference['workflow_id']}
        else:
            assert self.definition is not None,'A real read result is required before a proposal'
            proposed=deepcopy(self.definition);proposed['description']='중앙 대화에서 제안한 미저장 설명'
            for node in proposed['nodes'].values():
                if node['type']=='t':node['instructions']='중앙 대화 제안 · 사람 반영 전'
            self.proposed=deepcopy(proposed)
            arguments={'workflow_id':self.reference['workflow_id'],'base_revision':self.reference['revision'],'definition':proposed,'context_id':self.reference['context_id']}
        self.calls.append({'mode':self.mode,'function':candidates[0],'arguments':deepcopy(arguments)})
        return {'role':'assistant','content':None,'tool_calls':[{'id':'call_'+uuid4().hex,'type':'function','function':{'name':candidates[0],'arguments':json.dumps(arguments,ensure_ascii=False)}}]},'tool_calls'

    def reply_help(self,body,names):
        """Inspect the actual Native HTTP payload, then exercise its real callable."""
        assert len(names)==1 and (names[0]=='ees_workflow_view' or names[0].endswith('__ees_workflow_view')),names
        messages=body['messages'];last_user=max(i for i,item in enumerate(messages) if item['role']=='user')
        assert messages[last_user].get('content')==self.helper_question,messages[last_user]
        prefix='EES Work help context (read-only reference): '
        refs=[json.JSONDecoder().raw_decode(item['content'][len(prefix):])[0] for item in messages
              if isinstance(item.get('content'),str) and item['content'].startswith(prefix)]
        assert len(refs)==1 and refs[0].get('context_id') and refs[0].get('screen'),refs
        self.helper_payloads.append({'question':messages[last_user]['content'],'reference':deepcopy(refs[0]),
                                     'advertised_tool_names':names,'model':body.get('model')})
        results=[item for item in messages[last_user+1:] if item['role']=='tool']
        if results:
            self.tool_results.extend(deepcopy(results));value=self.find_help(results)
            assert value and value.get('ok') is True and value['help'].get('terms'),results
            assert value['help_context']=={'kind':'help',**refs[0]},value
            assert not any(key in value for key in ('workflow','run','historical','proposal')),value
            self.helper_results.append(deepcopy(value))
            return {'role':'assistant','content':self.helper_reply},'stop'
        # Supplying a real workflow ID cannot widen a helper request into a
        # workflow read. The actual wrapper must still return shipped help only.
        arguments={'workflow_id':self.helper_workflow}
        self.calls.append({'mode':'help','function':names[0],'arguments':arguments})
        return {'role':'assistant','content':None,'tool_calls':[{'id':'call_'+uuid4().hex,'type':'function',
            'function':{'name':names[0],'arguments':json.dumps(arguments)}}]},'tool_calls'

    @classmethod
    def find_help(cls,value):
        if isinstance(value,str):
            try:return cls.find_help(json.loads(value))
            except (ValueError,TypeError):return None
        if isinstance(value,dict):
            if isinstance(value.get('help'),dict) and isinstance(value.get('help_context'),dict):return value
            for item in value.values():
                if found:=cls.find_help(item):return found
        if isinstance(value,list):
            for item in value:
                if found:=cls.find_help(item):return found
        return None

    @classmethod
    def find_workflow(cls,value):
        if isinstance(value,str):
            try:return cls.find_workflow(json.loads(value))
            except (ValueError,TypeError):return None
        if isinstance(value,dict):
            if isinstance(value.get('workflow'),dict) and value['workflow'].get('draft'):return value['workflow']
            for item in value.values():
                if found:=cls.find_workflow(item):return found
        if isinstance(value,list):
            for item in value:
                if found:=cls.find_workflow(item):return found
        return None

    @classmethod
    def find_proposal(cls,value):
        if isinstance(value,str):
            try:return cls.find_proposal(json.loads(value))
            except (ValueError,TypeError):return None
        if isinstance(value,dict):
            if value.get('saved') is False and value.get('published') is False and isinstance(value.get('proposal'),dict):return value
            for item in value.values():
                if found:=cls.find_proposal(item):return found
        if isinstance(value,list):
            for item in value:
                if found:=cls.find_proposal(item):return found
        return None

    def close(self):
        self.server.shutdown();self.server.server_close();self.thread.join(3)


def central_flow(g):
    """All workflow writes and model sends below come from visible controls."""
    actor=g.api('/api/v1/auths/')['id']
    status=g.api('/api/v1/ees/assets/work-tool/status')
    source=(g.program/'open_webui/ees_workflow_tool.py').read_bytes()
    assert status['source_sha256']==hashlib.sha256(source).hexdigest()
    assert set(status['functions'])=={'ees_workflow_view','ees_workflow_propose','ees_workflow_display'},status
    setup=g.api('/api/v1/ees/assets/work-tool/setup',{
        'source_sha256':status['source_sha256'],'expected_token':status['expected_token'],
        'confirmation':'register_readonly_work_tool','access_grants':[{'principal_type':'user','principal_id':actor,'permission':'read'}]})
    assert setup['state']=='ready',setup
    registered=g.api('/api/v1/tools/id/ees_workflow')
    assert hashlib.sha256(registered['content'].encode()).hexdigest()==status['source_sha256']
    assert g.api('/api/ees-work/workspace')['workflows']==[]
    g.record('explicit packaged read-only Work tool registration',id='ees_workflow',source_sha256=status['source_sha256'],private_native_grant=True,model_presets_created=False)
    g.click('[data-action="mode"][data-mode="author"]');g.click('[data-author-action="create"]')
    g.click('[name=procedure_template][value=blank]');g.type('#ew-procedure-name','중앙 대화 제안 검증');g.click('[data-author-action=procedure_create]')
    g.wait('document.querySelector("[data-author-action=add_stage]")')
    g.click('[data-author-action=add_stage]');g.type('#ew-author-node [name=instructions]','저장된 기준 안내')
    g.click('[data-author-action=save]');g.wait('document.querySelector("#ees-work-designer")?.innerText.includes("초안 r2")')
    workflow=next(item for item in g.api('/api/ees-work/workspace')['workflows'] if item['name']=='중앙 대화 제안 검증')
    key=workflow['id'];before=g.api('/api/ees-work/workspace?workflow_id='+key)['workflow']
    assert before['revision']==2 and before['published_version'] is None
    # Establish an actual stored private Native chat before context-bound tools.
    g.native_socket_ready()
    g.type('#chat-input','중앙 대화 준비');g.click('#send-message-button')
    g.wait('location.pathname.startsWith("/c/") && document.querySelector("#chat-container")?.innerText.includes("중앙 대화의 합성 연결 준비 완료")',20000)
    chat_id=g.browser.evaluate('location.pathname.split("/").at(-1)')
    g.wait('window.__eesNativeWorkV1?.captureReference()?.workflow_id === '+json.dumps(key))
    reference=g.browser.evaluate('window.__eesNativeWorkV1.captureReference()')
    assert reference['revision']==before['revision'] and reference['kind']=='workspace'
    g.provider.reference=reference;g.provider.mode='read'
    g.type('#chat-input','중앙 도구로 현재 절차를 조회해 줘');g.click('#send-message-button')
    g.wait('document.querySelector("#chat-container")?.innerText.includes("중앙 도구 조회 완료")',20000)
    assert len(g.provider.calls)==1 and g.provider.calls[0]['mode']=='read',g.provider.calls
    assert g.provider.definition==before['draft']
    assert g.api('/api/ees-work/workspace?workflow_id='+key)['workflow']==before
    g.capture('native-central-read-tool')
    g.record('physical central chat executes actual registered authorized read',workflow_id=key,revision=before['revision'],stored_work_unchanged=True)
    g.provider.reference=g.browser.evaluate('window.__eesNativeWorkV1.captureReference()');g.provider.mode='propose'
    g.type('#chat-input','설명을 보완한 초안을 제안해 줘. 저장하지 말고 검토하게 해 줘');g.click('#send-message-button')
    g.wait('document.querySelector("#chat-container")?.innerText.includes("중앙 제안은 검토 전이며 저장하지 않았습니다")',20000)
    g.wait('document.querySelector("[data-author-action=ai_apply]")')
    assert len(g.provider.calls)==2 and g.provider.calls[1]['mode']=='propose',g.provider.calls
    assert g.api('/api/ees-work/workspace?workflow_id='+key)['workflow']==before
    assert g.browser.evaluate('document.querySelector("#ew-author-node [name=instructions]")?.value')=='저장된 기준 안내'
    if not g.browser.evaluate('document.querySelector(".ew-author-ai")?.open'):g.click('.ew-author-ai > summary')
    g.capture('native-central-proposal-before-human')
    g.click('[data-author-action=ai_apply]')
    g.wait('document.querySelector("#ew-author-node [name=instructions]")?.value === "중앙 대화 제안 · 사람 반영 전"')
    assert g.api('/api/ees-work/workspace?workflow_id='+key)['workflow']==before
    g.capture('native-central-human-applied-unsaved')
    g.click('[data-author-action=save]');g.wait('document.querySelector("#ees-work-designer")?.innerText.includes("초안 r3")')
    after=g.api('/api/ees-work/workspace?workflow_id='+key)['workflow']
    assert after['revision']==3 and after['draft']==g.provider.proposed and after['published_version'] is None
    assert g.api('/api/ees-work/workspace')['runs']==[]
    chat=g.api('/api/v1/chats/'+chat_id)['chat']
    recorded=json.dumps(chat,ensure_ascii=False)
    assert 'ees_workflow_view' in recorded and 'ees_workflow_propose' in recorded,'Native chat must preserve actual tool-call history'
    g.capture('native-central-human-saved-draft')
    g.record('physical central proposal then separate apply and save',draft_revision=3,published=False,runs=0,chat_id=chat_id,native_tool_history_saved=True,model_boundary='Loopback synthetic tool-call selection only; actual Native registered tool execution')
    input_and_history_flow(g,key,chat_id)
    helper_chat_flow(g,key,chat_id)


def input_and_history_flow(g,key,chat_id):
    """Real input suggestion plus immutable message-reference lookup."""
    g.provider.mode='plain'
    # Extend the same authored draft with an actual declared human task, using
    # the same visible editor controls a user uses; no seeded procedure/API write.
    g.click('[data-author-action=node][data-id=""]');g.click('[data-author-action=add_job]')
    g.type('#ew-author-node [name=name]','입력 제안과 과거 근거')
    g.click('[data-author-action=input_add]');g.type('#ees-work-dialog [name=name]','자료 메모')
    g.type('#ees-work-dialog [name=id]','note');g.click('#ees-work-dialog [data-dialog-confirm]')
    g.click('[data-author-action=save]');g.wait('!document.querySelector("[data-author-action=validate]")?.disabled')
    g.click('[data-author-action=validate]');g.click('[data-author-action=publish]');g.click('#ees-work-dialog [data-dialog-confirm]')
    g.wait('document.querySelector("#ees-work-designer")?.innerText.includes("게시 v1")')
    g.click('[data-action=mode][data-mode=work]');g.click('[data-action=workflow][data-workflow-id="'+key+'"]')
    g.click('[data-action=start_run][data-start-inline]')
    g.wait('document.querySelector("[data-action=job]")')
    run=g.api('/api/ees-work/workspace?workflow_id='+key)['runs'][0];run_id=run['id']
    assert run['workflow_id']==key and run['version']==1 and run['status']=='open' and not run['attempts'],run
    g.wait_work_ready(workflow_id=key,run_id=run_id)
    job=next(node for node in run['definition']['nodes'].values() if node['type']=='j')
    g.click('[data-action=job][data-job-id="'+job['id']+'"]')
    before=g.api('/api/ees-work/workspace?run_id='+run_id)['run']
    g.click('[data-action=propose_inputs]');g.type('#ees-input-proposal-prompt','개발용 자료 메모를 제안해 줘. 저장하지 마.')
    if g.browser.evaluate('!!document.querySelector("#ees-input-proposal-model")'):
        # Native select is changed by physical keyboard input, never DOM value.
        index=g.browser.evaluate('[...document.querySelector("#ees-input-proposal-model").options].findIndex(option=>option.value === "c3-synthetic-model")')
        assert index>=0,'The approved synthetic model must be an actual offered choice'
        g.click('#ees-input-proposal-model')
        for kind in ('keyDown','keyUp'):g.browser.call('Input.dispatchKeyEvent',{'type':kind,'key':'Home','windowsVirtualKeyCode':36})
        for _ in range(index):
            for kind in ('keyDown','keyUp'):g.browser.call('Input.dispatchKeyEvent',{'type':kind,'key':'ArrowDown','windowsVirtualKeyCode':40})
        for kind in ('keyDown','keyUp'):g.browser.call('Input.dispatchKeyEvent',{'type':kind,'key':'Enter','windowsVirtualKeyCode':13})
        assert g.browser.evaluate('document.querySelector("#ees-input-proposal-model").value')=='c3-synthetic-model'
    g.click('#ees-work-dialog [data-dialog-confirm]');g.wait('document.querySelector("[data-action=apply_input_proposal]")')
    assert len(g.provider.input_proposals)==1
    assert g.api('/api/ees-work/workspace?run_id='+run_id)['run']==before
    assert g.browser.evaluate('document.querySelector("[data-work-input][name=note]").value')==''
    g.capture('input-proposal-before-human')
    g.click('[data-action=apply_input_proposal]')
    g.wait('document.querySelector("[data-work-input][name=note]")?.value === "AI가 제안한 첫 입력"')
    assert g.api('/api/ees-work/workspace?run_id='+run_id)['run']==before
    g.click('[data-action=save_inputs]');g.wait('!document.querySelector("[data-action=save_inputs]")?.disabled')
    saved=g.api('/api/ees-work/workspace?run_id='+run_id)['run']
    assert saved['inputs']=={'note':'AI가 제안한 첫 입력'} and saved['attempts']==[]
    g.capture('input-proposal-human-saved-not-executed')
    g.record('physical input suggestion preview apply then separate save',run_id=run_id,proposal_count=1,attempts=0)
    g.click('[data-action=confirm]');g.click('#ees-work-dialog [data-dialog-confirm]')
    g.wait('document.querySelector("#ees-work-panel .ew-status[data-status=completed]")')
    first=g.api('/api/ees-work/workspace?run_id='+run_id)['run'];assert len(first['attempts'])==1
    first_attempt=first['attempts'][0]
    g.provider.plain_reply='첫 번째 완료 근거를 참조한 대화 응답'
    question='첫 번째 완료 근거를 대화에 남겨 줘'
    g.type('#chat-input',question);g.click('#send-message-button')
    g.wait('document.querySelector("#chat-container")?.innerText.includes("첫 번째 완료 근거를 참조한 대화 응답")',20000)
    chat=g.api('/api/v1/chats/'+chat_id)['chat']
    message=next(item for item in chat['history']['messages'].values() if item.get('role')=='user' and item.get('content')==question)
    ref=message['meta']['ees_work_reference']
    assert ref['attempt_id']==first_attempt['id'] and ref['version']==1 and ref['result_revision']==1,ref
    assert ref.get('created_at')==first['updated_at'],ref
    g.type('[data-work-input][name=note]','나중에 저장한 두 번째 입력')
    g.click('[data-action=save_inputs]');g.wait('!document.querySelector("[data-action=save_inputs]")?.disabled')
    g.click('[data-action=confirm]');g.click('#ees-work-dialog [data-dialog-confirm]')
    g.wait('document.querySelector("#ees-work-panel .ew-status[data-status=completed]")')
    latest=g.api('/api/ees-work/workspace?run_id='+run_id)['run'];assert len(latest['attempts'])==2
    assert latest['attempts'][0]==first_attempt
    selector='#message-'+message['id']+' [data-ees-reference-slot] [data-action=open_reference]'
    g.wait('document.querySelector('+json.dumps(selector)+')')
    card=g.browser.evaluate('document.querySelector('+json.dumps(selector)+').innerText')
    assert '기준 시각' in card and '기록 없음' not in card,card
    g.click(selector)
    g.wait('document.querySelector("#ees-work-panel")?.innerText.includes("대화에서 참조한 과거 기록")')
    g.click('#ees-work-panel .ew-history summary')
    visible=g.browser.evaluate('document.querySelector("#ees-work-panel").innerText')
    assert 'AI가 제안한 첫 입력' in visible and '나중에 저장한 두 번째 입력' not in visible
    assert not g.browser.evaluate('!!document.querySelector("#ees-work-panel [data-mutation]")')
    assert g.api('/api/ees-work/workspace?run_id='+run_id)['run']==latest
    g.capture('native-message-reference-exact-old-attempt')
    g.record('physical immutable historical message reference after second attempt',message_id=message['id'],attempt_id=first_attempt['id'],latest_attempts=2,readonly=True)


def helper_chat_flow(g,key,chat_id):
    """Physical helper send, actual isolated tool dispatch, then live ACL denial."""
    before=g.api('/api/ees-work/workspace?workflow_id='+key)
    g.click('[data-action=mode][data-mode=author]')
    g.click('[data-author-action=list]');g.click('[data-author-action=create]')
    selector='#ees-work-procedure-start [data-action=procedure_question]'
    g.wait('document.querySelector('+json.dumps(selector)+') && !document.querySelector('+json.dumps(selector)+').disabled')
    question=g.browser.evaluate('document.querySelector('+json.dumps(selector)+').innerText.trim()')
    assert question
    draft='업무 도우미 질문과 함께 보내지 않을 작성 중인 글'
    g.type('#chat-input',draft)
    prior_chat=g.api('/api/v1/chats/'+chat_id)['chat'];count=len(prior_chat['history']['messages'])
    event_start=len(g.browser.events);call_start=len(g.provider.calls)
    g.provider.mode='help';g.provider.helper_question=question;g.provider.helper_workflow=key
    g.click(selector)
    g.wait('document.querySelector("#chat-container")?.innerText.includes('+json.dumps(g.provider.helper_reply)+')',20000)
    chat=g.completed_chat(chat_id,count+2)
    users=[item for item in chat['history']['messages'].values() if item.get('role')=='user' and item.get('content')==question]
    assert len(users)==1,users
    message=users[0];reference=deepcopy(message['meta']['ees_work_reference'])
    assert reference['kind']=='help' and reference['screen']=='새 업무 절차' and reference['context_id'],reference
    assert message['meta'].get('ees_work_help')==1,message
    assert not message.get('files') and message.get('models')==['c3-synthetic-model'],message
    assert g.browser.evaluate('document.querySelector("#chat-input").innerText')==draft
    assert len(g.provider.calls)==call_start+1 and g.provider.calls[-1]['mode']=='help',g.provider.calls
    assert len(g.provider.helper_results)==1
    assert g.provider.helper_payloads[-1]['reference']=={name:value for name,value in reference.items() if name!='kind'}
    user_selector='#message-'+message['id']
    g.wait('document.querySelector('+json.dumps(user_selector+' [data-ees-helper-reference]')+')')
    assert g.browser.evaluate('!!document.querySelector("[data-ees-helper-label]")')
    # Retain the real browser request as a local template without persisting its
    # credentials/session ID into evidence. Later API probes change only inputs.
    requests=[event['params']['request'] for event in g.browser.events[event_start:]
              if event.get('method')=='Network.requestWillBeSent'
              and event.get('params',{}).get('request',{}).get('url','').endswith('/api/chat/completions')]
    candidates=[json.loads(item['postData']) for item in requests if item.get('postData')]
    template=next(item for item in candidates if (item.get('user_message') or {}).get('content')==question)
    assert template['user_message']['meta']['ees_work_reference']==reference
    g.capture('native-helper-question-only-and-reference')
    g.record('physical helper question directly sends through actual Native model and read-only tool',
             chat_id=chat_id,message_id=message['id'],question=question,reference=reference,
             selected_model='c3-synthetic-model',advertised_tools=g.provider.helper_payloads[-1]['advertised_tool_names'],
             actual_tool_results=1,composer_preserved=True,workflow_argument_cannot_read_work=True)

    g.click('[data-action=mode][data-mode=work]')
    g.navigate('/c/'+chat_id)
    g.wait('document.querySelector('+json.dumps(user_selector+' [data-ees-helper-reference]')+')')
    stored=g.api('/api/v1/chats/'+chat_id)['chat']['history']['messages'][message['id']]
    assert stored['content']==question and stored['meta']['ees_work_reference']==reference
    after=g.api('/api/ees-work/workspace?workflow_id='+key)
    assert after['workflow']==before['workflow'] and after['runs']==before['runs']
    g.capture('native-helper-reference-reloaded')
    g.record('helper reference remains immutable after navigation and actual persisted-chat reload',
             message_id=message['id'],reference=reference,work_unchanged=True)

    # Probe the server boundary with a valid helper request containing unrelated
    # selected features. Fake selections would fail Native resolution if the
    # product did not remove them before the existing loading/dispatch paths.
    saved_chat_models=['c3-synthetic-model','c3-synthetic-model']
    saved_chat_files=[{'type':'file','id':'preserved-chat-file','name':'synthetic-existing-metadata.txt'}]
    g.api('/api/v1/chats/'+chat_id,{'chat':{'models':saved_chat_models,'files':saved_chat_files}})
    injected=helper_request(template,chat_id,reference,'선택된 기능과 자료 없이 도움말만 알려 주세요',
                            parent_id=chat['history']['currentId'])
    injected.update(tool_ids=['helper-selected-tool-must-not-load'],filter_ids=['helper-selected-filter-must-not-load'],
                    skill_ids=['helper-selected-skill-must-not-load'],terminal_id='helper-terminal-must-not-load',
                    features={'web_search':True,'image_generation':True,'code_interpreter':True},
                    files=[{'type':'file','id':'helper-file-must-not-read'}],
                    tool_servers=[{'url':'http://127.0.0.1:1/helper-must-not-connect','type':'openapi'}])
    injected['user_message']['files']=deepcopy(injected['files'])
    g.provider.helper_question=injected['user_message']['content']
    calls=len(g.provider.calls);g.api('/api/chat/completions',injected)
    chat=g.completed_chat(chat_id,count+4)
    isolated=chat['history']['messages'][injected['user_message']['id']]
    assert isolated['content']==g.provider.helper_question and not isolated.get('files'),isolated
    assert isolated['models']==['c3-synthetic-model']
    assert chat['models']==saved_chat_models and chat['files']==saved_chat_files,chat
    assert len(g.provider.calls)==calls+1 and g.provider.calls[-1]['mode']=='help'
    assert len(g.provider.helper_results)==2
    assert g.provider.helper_payloads[-1]['advertised_tool_names']==g.provider.helper_payloads[0]['advertised_tool_names']
    final_work=g.api('/api/ees-work/workspace?workflow_id='+key)
    assert final_work['workflow']==before['workflow'] and final_work['runs']==before['runs']
    g.record('actual helper call boundary strips selected tools filters skills files terminal and features',
             message_id=isolated['id'],actual_helper_results=2,advertised_tools=g.provider.helper_payloads[-1]['advertised_tool_names'],
             unrelated_asset_resolution=False,stored_message_files=0,
             existing_chat_models_preserved=saved_chat_models,existing_chat_file_metadata_preserved=True)
    fresh=helper_request(template,'',reference,'새 대화에서도 업무 도우미가 하나의 안내만 답해 주세요')
    fresh['ees_work_composer_models']=saved_chat_models
    g.provider.helper_question=fresh['user_message']['content'];calls=len(g.provider.calls)
    created=g.api('/api/chat/completions',fresh)
    assert created['chat_id']!=chat_id,created
    new_chat=g.completed_chat(created['chat_id'],2)
    assert new_chat['models']==saved_chat_models,new_chat
    new_user=new_chat['history']['messages'][fresh['user_message']['id']]
    assert new_user['models']==['c3-synthetic-model'] and not new_user.get('files'),new_user
    assert new_user['meta']['ees_work_reference']==reference
    assert len(g.provider.calls)==calls+1 and len(g.provider.helper_results)==3
    g.record('actual new helper chat preserves multiple composer models with one assistant answer',
             chat_id=created['chat_id'],stored_chat_models=saved_chat_models,stored_messages=2,
             assistant_messages=1,actual_helper_results=3)
    helper_denial_flow(g,template)


def helper_request(template,chat_id,reference,question,*,parent_id=None,model='c3-synthetic-model'):
    body=deepcopy(template);user_id=str(uuid4());assistant_id=str(uuid4())
    body.update(model=model,chat_id=chat_id,parent_id=parent_id,
                messages=[{'role':'user','content':question}],
                message_ids=[{'model_id':model,'message_id':assistant_id}],
                user_message={'id':user_id,'parentId':parent_id,'childrenIds':[assistant_id],
                              'role':'user','content':question,'models':[model],
                              'timestamp':int(time.time()),'meta':{'ees_work_help':1,'ees_work_reference':deepcopy(reference)}})
    body.pop('id',None);body.pop('model_item',None)
    return body


def helper_denial_flow(g,template):
    """Real member and Native ACL APIs: failure is before persistence/provider."""
    model='c3-synthetic-model'
    member=g.api('/api/v1/auths/add',{'name':'Helper ACL synthetic member',
                 'email':'helper-'+uuid4().hex+'@example.test','password':uuid4().hex+'Ab1!','role':'user'})
    headers={'Authorization':'Bearer '+member['token']}
    grants=[{'principal_type':'user','principal_id':member['id'],'permission':'read'}]
    g.api('/api/v1/tools/id/ees_workflow/access/update',{'access_grants':grants})
    g.api('/api/v1/models/model/access/update',{'id':model,'name':'Synthetic helper model','access_grants':grants})
    chat=g.api('/api/v1/chats/new',{'chat':{'title':'Helper denial fixture','models':[model],
               'history':{'messages':{},'currentId':None},'messages':[]}},headers=headers)
    chat_id=chat['id'];reference={'kind':'help','system_id':'','context_id':'member-help-boundary','screen':'새 업무 절차','title':'새 업무 절차'}
    def readiness(model_id=model):
        return g.api('/api/ees-work/help/status?'+urlencode({'model_id':model_id,'chat_id':chat_id}),headers=headers)
    assert readiness().get('available') is True

    def blocked(label,*,model_id=model,reason=None):
        status=readiness(model_id);assert status['available'] is False,status
        before=g.api('/api/v1/chats/'+chat_id,headers=headers)['chat'];providers=len(g.provider.models)
        chat_list=g.api('/api/v1/chats/',headers=headers)
        body=helper_request(template,chat_id,reference,'보내지 않아야 하는 업무 도움말 질문',model=model_id)
        body.pop('session_id',None)
        response=g.client.post('/api/chat/completions',headers=headers,json=body)
        assert response.status_code in {400,401,403,409},(label,response.status_code,response.text[:500])
        detail=response.json().get('detail')
        if reason is not None:
            assert response.status_code==409 and isinstance(detail,dict) and detail.get('code')=='work_help_unavailable' and detail.get('reason')==reason and detail.get('persisted') is False,(label,detail)
        assert g.api('/api/v1/chats/'+chat_id,headers=headers)['chat']==before,label
        assert len(g.provider.models)==providers,label
        # A root-message attempt must not create an empty chat or assistant
        # placeholder either. Exercise both branches of Native persistence.
        body['chat_id']='';body['parent_id']=None
        fresh=g.client.post('/api/chat/completions',headers=headers,json=body)
        assert fresh.status_code==response.status_code,(label,fresh.status_code,fresh.text[:500])
        assert g.api('/api/v1/chats/',headers=headers)==chat_list,label
        assert len(g.provider.models)==providers,label
        g.record('helper unavailable before Native persistence and external model: '+label,
                 status=response.status_code,readiness_code=status.get('code'),
                 messages_before=len(before['history']['messages']),messages_after=len(before['history']['messages']),
                 provider_calls=0,new_chat_created=False,synthetic_member=True)

    blocked('missing selected model',model_id='helper-model-not-installed')
    g.api('/api/v1/models/model/access/update',{'id':model,'access_grants':[]})
    blocked('revoked selected model')
    g.api('/api/v1/models/model/access/update',{'id':model,'access_grants':grants})
    assert readiness().get('available') is True
    g.api('/api/v1/tools/id/ees_workflow/access/update',{'access_grants':[]})
    blocked('revoked helper tool',reason='work_chat_access_denied')
    g.api('/api/v1/tools/id/ees_workflow/access/update',{'access_grants':grants})
    assert readiness().get('available') is True
    g.api('/api/v1/tools/id/ees_workflow/delete',method='DELETE')
    blocked('missing helper tool',reason='work_chat_tool_unconfigured')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel',type=Path,required=True);parser.add_argument('--chrome',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    with patch.object(integrated,'SyntheticProvider',NativeToolProvider):g=NativeChatGate(args)
    try:
        g.setup();central_flow(g);assert not g.provider.errors,g.provider.errors
        g.report['status']='passed';g.write_report()
    except BaseException as error:
        g.report['status']='failed';g.report['failure']={'type':type(error).__name__,'message':str(error)[:1200]}
        try:g.capture('failure')
        except Exception as capture:g.report['capture_error']=type(capture).__name__+': '+str(capture)[:300]
        raise
    finally:
        # Preserve the actual application error body before Chrome/temp DATA_DIR
        # shutdown, so a model mismatch is not guessed from an HTTP status.
        g.report['api_failures']=[]
        if g.browser and g.browser.session:
            try:
                chat_id=g.browser.evaluate('location.pathname.startsWith("/c/") ? location.pathname.split("/").at(-1) : ""')
                if chat_id:
                    record=g.api('/api/v1/chats/'+chat_id)['chat']
                    g.report['native_messages']=[{key:item.get(key) for key in ('id','role','content','done','meta')} for item in record.get('history',{}).get('messages',{}).values()]
            except Exception as error:g.report['native_message_capture_error']=type(error).__name__+': '+str(error)[:300]
        if g.browser and g.browser.session:
            for event in g.browser.events:
                response=event.get('params',{}).get('response',{})
                if event.get('method')!='Network.responseReceived' or '/api/ees-work/' not in response.get('url','') or response.get('status',0)<400:continue
                item={'path':response['url'].split(g.base)[-1].split('?')[0],'status':response['status']}
                try:item['body']=g.browser.call('Network.getResponseBody',{'requestId':event['params']['requestId']}).get('body','')[:2000]
                except Exception as error:item['capture_error']=type(error).__name__+': '+str(error)[:200]
                g.report['api_failures'].append(item)
        g.report['model_boundary']={'calls':g.provider.calls,'models':g.provider.models,'tool_results':g.provider.tool_results,'input_proposals':g.provider.input_proposals,'helper_payloads':g.provider.helper_payloads,'helper_results':g.provider.helper_results,'errors':g.provider.errors}
        g.write_report();g.close()


if __name__=='__main__':main()
