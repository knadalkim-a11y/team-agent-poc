from copy import deepcopy
import json, unittest
from pathlib import Path
from ees_work_integrated_fixture import IntegratedNativeCase
from test_ees_helper_chat_native import install_helper_status_fixture, QUESTION, ANSWER

class ExistingWorkflowHelperProbe(IntegratedNativeCase):
 def runTest(self):
  install_helper_status_fixture(self)
  key=self.author(jobs=1)
  run=self.start(key)
  self.open_run(key,run)
  before=self.state(workflow_id=key)
  self.click('[data-action=mode][data-mode=author]')
  self.wait('document.querySelector("[data-author-action=list]")')
  self.assertFalse(self.browser.evaluate('!!document.querySelector("[data-author-action=create]")'))
  editor=self.text('#ees-work-panel')
  self.assertIn('업무 절차 목록',editor)
  self.screenshot('helper-entry-existing-editor')
  self.click('[data-author-action=list]');self.click('[data-author-action=create]')
  self.wait('document.querySelector('+json.dumps(QUESTION)+') && !document.querySelector('+json.dumps(QUESTION)+').disabled')
  question=self.text(QUESTION).strip()
  self.assertTrue(question)
  draft='업무 도우미 질문과 함께 보내지 않을 작성 중인 글'
  self.fill('#chat-input',draft)
  count=len(self.server.chats['existing-chat']['chat']['history']['messages'])
  self.click(QUESTION)
  self.wait('document.querySelector("#chat-container")?.innerText.includes('+json.dumps(ANSWER)+') && !window.__eesSourceShellV1.helpState().busy')
  self.assertEqual(len(self.server.completions),1)
  request=self.server.completions[-1]; message=request['user_message']
  self.assertEqual(message['content'],question)
  self.assertEqual(message['meta']['ees_work_help'],1)
  reference=deepcopy(message['meta']['ees_work_reference'])
  self.assertEqual(reference['kind'],'help');self.assertEqual(reference['screen'],'새 업무 절차');self.assertTrue(reference['context_id'])
  self.assertFalse(message.get('files'));self.assertEqual(message['models'],['fixture-model'])
  self.assertEqual(self.text('#chat-input'),draft)
  selector='#message-'+message['id']+' [data-ees-helper-reference]'
  self.wait('document.querySelector('+json.dumps(selector)+') && document.querySelector("[data-ees-helper-label]")')
  self.assertEqual(len(self.server.chats['existing-chat']['chat']['history']['messages']),count+2)
  self.screenshot('helper-existing-editor-question-only-and-reference')
  self.click('[data-action=mode][data-mode=work]')
  self.navigate('/c/existing-chat')
  self.wait('window.__eesNativeDraftV1?.ready() && document.querySelector('+json.dumps(selector)+') && document.querySelector("[data-ees-helper-label]")')
  stored=self.server.chats['existing-chat']['chat']['history']['messages'][message['id']]
  self.assertEqual(stored['content'],question);self.assertEqual(stored['meta']['ees_work_reference'],reference)
  after=self.state(workflow_id=key)
  self.assertEqual(after['workflow'],before['workflow']);self.assertEqual(after['runs'],before['runs'])
  self.assertEqual(len(self.server.completions),1)
  self.screenshot('helper-existing-editor-fixed-reference-after-reload')
  Path('/tmp/helper-existing-workflow-probe.json').write_text(json.dumps({'scope':'Real compiled source UI, Chrome153 and Work SQLite; synthetic Native account/chat storage, helper permission and model transport. Does not prove full Native CLI/tool/ACL gate.','wheel_sha256':'6953639186f062f24ac851502d05831a1a67acc7ca2164140faeb4557ada1863','initial_editor':editor,'initial_create_count':0,'entry':'author -> list -> create','question':question,'reference':reference,'composer_preserved':True,'completion_count':1,'same_chat_reloaded':True,'work_unchanged':True},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

unittest.main(verbosity=2)
