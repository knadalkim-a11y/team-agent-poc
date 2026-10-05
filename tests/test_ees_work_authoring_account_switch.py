"""Actual Native logout/signin and ACLs; synthetic, delayed model transport.

Both browser tabs share one Chrome profile. No token or storage event is forged.
The current integrated workspace replaces the retired process/demo editor.
"""
from copy import deepcopy
import json
import threading
import unittest
from uuid import uuid4

import test_ees_work_authoring_native as native


class NativeAuthoringAccountSwitchTests(unittest.TestCase):
    setUpClass = classmethod(native.NativeAuthoringBrowserTests.setUpClass.__func__)
    for _name in ('setUp','tearDown','evidence_directory','screenshot','capture_failure_evidence',
                  'api','wait','eventually','browser_api','click_text','login_ui','logout_ui',
                  'select_native','assert_user_workspace_zero','open_sidebar','enter_authoring','work_command'):
        locals()[_name] = getattr(native.NativeAuthoringBrowserTests, _name)

    def activate_tab(self, session):
        self.browser.session = session
        self.browser.call('Page.bringToFront')
        self.wait("document.visibilityState === 'visible' && document.hasFocus()")

    def authoring_content(self):
        return self.browser.evaluate("(()=>{const root=document.querySelector('#ees-work-designer');return [root?.textContent||'',...[...(root?.querySelectorAll('input,textarea')||[])].map(e=>e.value)].join('\\n')})()")

    def arrange_account(self, suffix, system):
        email = 'switch.' + suffix.lower() + '@example.test'
        response = self.api('POST','/api/v1/auths/signup',{'name':'합성 계정 '+suffix,'email':email,'password':'Fixture-person-only-42!'})
        self.assertEqual(response.status_code,200,response.text); account=response.json()
        self.assertEqual(account['role'],'pending')
        response=self.api('POST','/api/v1/users/'+account['id']+'/update',{'role':'user'},self.admin['token'])
        self.assertEqual(response.status_code,200,response.text)
        group=self.api('POST','/api/v1/groups/create',{'name':system+' synthetic group','permissions':{},'description':'Temporary Native membership fixture'},self.admin['token'])
        self.assertEqual(group.status_code,200,group.text)
        response=self.api('POST','/api/v1/groups/id/'+group.json()['id']+'/users/add',{'user_ids':[account['id']]},self.admin['token'])
        self.assertEqual(response.status_code,200,response.text)
        response=self.api('POST','/api/ees-work/workspace/command',{'action':'save_access','system_id':system,'factory_id':'*','principal_kind':'group','principal_id':group.json()['id'],'roles':['manager','participant'],'expected_revision':0,'request_id':str(uuid4())},self.admin['token'])
        self.assertEqual(response.status_code,200,response.text)
        signed=self.fixture.run(self.fixture.signin(email,'Fixture-person-only-42!'))
        settings=self.api('POST','/api/v1/users/user/settings/update',{'ui':{'params':{'system':'NU05 private Native setting '+suffix},'chatBubble':suffix=='B'}},signed['token'])
        self.assertEqual(settings.status_code,200,settings.text)
        created=self.api('POST','/api/ees-work/workspace/command',{'action':'create_workflow','name':suffix+' 전용 합성 절차','system_id':system,'expected_revision':0,'request_id':str(uuid4())},signed['token'])
        self.assertEqual(created.status_code,200,created.text)
        return signed,created.json()['workflow']

    def open_workflow(self, workflow):
        self.enter_authoring()
        selector='[data-author-action="open"][data-id="'+workflow['id']+'"]'
        self.wait('document.querySelector('+json.dumps(selector)+')')
        self.click(selector)
        self.wait("document.querySelector('[data-author-action=edit_workflow]')")
        self.click('[data-author-action="add_stage"]')
        self.wait("document.querySelector('#ew-author-node [name=instructions]')")
        self.assert_user_workspace_zero()

    def test_same_profile_native_logout_login_discards_late_a_read_and_ai(self):
        account_a,workflow_a=self.arrange_account('A','EMS')
        account_b,workflow_b=self.arrange_account('B','FDC')
        from native_ui_fixture import chat_record
        for identifier,account,title in [('private-account-a-chat',account_a,'NU05 A private chat title'),('private-account-b-chat',account_b,'NU05 B current chat title')]:
            record=chat_record(identifier);record['user_id']=account['id'];record['title']=record['chat']['title']=title
            self.fixture.chats[identifier]=record
        a_text='A만의 저장하지 않은 수행 안내';a_question='A의 비공개 작성 질문';a_answer='늦게 도착한 계정 A 전용 응답';b_text='B가 현재 직접 작성한 수행 안내'
        self.login_ui(account_a['email'],'Fixture-person-only-42!');self.open_workflow(workflow_a)
        self.click('[data-ees-panel-resize]');self.key('End',35)
        self.wait("document.querySelector('#ees-work-panel')?.getBoundingClientRect().width===720")
        self.eventually(lambda: self.browser_api('GET','/api/ees-work/workspace')['data'].get('ui_state',{}).get('state',{}).get('selection',{}).get('panel_width')==720)
        self.fill('#ew-author-node [name=instructions]',a_text)
        self.click('[data-author-action=node][data-id=""]')
        self.click('.ew-author-ai > summary');self.fill('[name=ai_prompt]',a_question)
        self.wait("!document.querySelector('[data-author-action=ai_propose]')?.disabled")
        self.server.proposal_answer=a_answer
        proposal={'workflow_id':workflow_a['id'],'started':threading.Event(),'release':threading.Event(),'finished':threading.Event()}
        self.server.proposal_gate=proposal;self.addCleanup(proposal['release'].set)
        self.click('[data-author-action=ai_propose]');self.assertTrue(proposal['started'].wait(5),'A authorized proposal did not reach response barrier')
        self.assertIn(a_text,json.dumps(self.server.proposal_requests[-1],ensure_ascii=False))
        read={'actor_id':account_a['id'],'workflow_id':workflow_a['id'],'started':threading.Event(),'release':threading.Event(),'finished':threading.Event()}
        self.server.authoring_read_gate=read;self.addCleanup(read['release'].set)
        self.browser.evaluate('void window.__eesNativeWorkV1.refresh()')
        self.assertTrue(read['started'].wait(5),'A authorized workspace read did not reach response barrier')
        old_session=self.browser.session
        self.browser.navigate('about:blank');self.browser.call('Runtime.enable');self.browser.call('Network.enable')
        self.navigate('/');self.wait("document.querySelector('#chat-input.ProseMirror')")
        self.logout_ui(account_a['name']);self.login_ui(account_b['email'],'Fixture-person-only-42!');self.open_workflow(workflow_b)
        self.assertEqual(self.browser.evaluate("document.querySelector('#ees-work-panel').getBoundingClientRect().width"),480)
        self.click('[data-ees-panel-resize]');self.key('Home',36)
        self.wait("document.querySelector('#ees-work-panel')?.getBoundingClientRect().width===400")
        self.eventually(lambda: self.browser_api('GET','/api/ees-work/workspace')['data'].get('ui_state',{}).get('state',{}).get('selection',{}).get('panel_width')==400)
        self.fill('#ew-author-node [name=instructions]',b_text);new_session=self.browser.session
        self.assertEqual(self.browser_api('GET','/api/v1/auths/')['data']['id'],account_b['id'])
        settings=self.browser_api('GET','/api/v1/users/user/settings')['data']
        self.assertEqual(settings['ui']['params']['system'],'NU05 private Native setting B')
        self.assertNotIn('NU05 private Native setting A',json.dumps(settings))
        self.assertEqual([row['id'] for row in self.browser_api('GET','/api/v1/chats/?page=1')['data']],['private-account-b-chat'])
        self.assertEqual(self.browser_api('GET','/api/v1/chats/private-account-a-chat')['status'],403)
        self.assertEqual(self.browser_api('GET','/api/v1/chats/private-account-b-chat')['status'],200)
        read['release'].set();proposal['release'].set()
        self.assertTrue(read['finished'].wait(5));self.assertTrue(proposal['finished'].wait(5))
        self.assertEqual(self.read('#ew-author-node [name=instructions]','value'),b_text)
        for secret in (a_text,a_question,a_answer,'NU05 A private chat title'):
            self.assertNotIn(secret,self.authoring_content()+self.text('body'))
        self.screenshot('sa26-b-after-late-a-responses')
        self.activate_tab(old_session)
        self.wait("document.querySelector('#ees-work-system-trigger')?.textContent.includes('FDC')")
        self.assertEqual(self.browser_api('GET','/api/v1/auths/')['data']['id'],account_b['id'])
        # This background tab restored B before B changed the preference. Its
        # active display may stay at B's previous width, never A's private 720.
        self.assertNotEqual(self.browser.evaluate("document.querySelector('#ees-work-panel').getBoundingClientRect().width"),720)
        for secret in (a_text,a_question,a_answer):self.assertNotIn(secret,self.authoring_content())
        self.assertEqual(self.browser_api('GET','/api/v1/users/user/settings')['data']['ui']['params']['system'],'NU05 private Native setting B')
        self.screenshot('nu05-former-a-tab-now-b')
        self.activate_tab(new_session);self.server.proposal_gate=None;self.server.authoring_read_gate=None
        self.server.proposal_answer='B만의 합성 응답'
        self.click('[data-author-action=node][data-id=""]')
        self.click('.ew-author-ai > summary');self.fill('[name=ai_prompt]','현재 B 절차 설명')
        self.click('[data-author-action=ai_propose]');self.wait("document.querySelector('[data-author-action=ai_apply]')")
        self.click('.ew-author-stage [data-author-action=node]')
        context=json.dumps(self.server.proposal_requests[-1],ensure_ascii=False)
        self.assertIn(b_text,context)
        for secret in (a_text,a_question,a_answer):self.assertNotIn(secret,context)
        self.assertEqual(self.read('#ew-author-node [name=instructions]','value'),b_text)
        # After all original late-response/privacy assertions, reloading the
        # former A tab must restore the latest stored B preference.
        self.activate_tab(old_session);self.navigate('/')
        self.wait("document.querySelector('#ees-work-panel')?.getBoundingClientRect().width===400")
        self.activate_tab(new_session)
        for account,workflow in ((account_a,workflow_a),(account_b,workflow_b)):
            stored=self.api('GET','/api/ees-work/workspace?workflow_id='+workflow['id'],token=account['token'])
            self.assertEqual(stored.status_code,200,stored.text)
            self.assertEqual(stored.json()['ui_state']['state']['selection']['panel_width'],720 if account['id']==account_a['id'] else 400)
            self.assertEqual(stored.json()['workflow']['revision'],workflow['revision'])
            self.assertEqual(stored.json()['workflow']['draft'],workflow['draft'])
        (self.evidence_directory()/'sa26-nu05-account-switch.json').write_text(json.dumps({'same_profile':True,'native_logout_signin_ui':True,'actual_native_acl':True,'delayed_authenticated_a_read_and_proposal':True,'b_unsaved_draft_preserved':True,'old_tab_a_private_state_cleared':True,'b_model_context_excludes_a':True,'native_settings_and_chat_ownership_separate':True,'private_panel_widths':{'A':720,'B':400},'automatic_authoring_persistence':False,'synthetic_boundary':'Only model transport/chat storage are synthetic; Native auth, users, membership, ACL and workspace storage are real.'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    unittest.main()
