import json,unittest
from pathlib import Path
from ees_work_integrated_fixture import IntegratedNativeCase
class ReferenceSlotProbe(IntegratedNativeCase):
 def runTest(self):
  key=self.author(jobs=1,fields=[{'id':'note','name':'자료 메모','type':'text','scope':'run'}])
  run=self.start(key)
  run=self.command('save_inputs',run_id=run['id'],expected_revision=run['revision'],values={'note':'첫 번째 입력'})['run']
  first=self.command('human_confirm',run_id=run['id'],job_id='job-0',expected_revision=run['revision'])['run']
  attempt=first['attempts'][0]
  reference={'kind':'workspace','workflow_id':key,'run_id':run['id'],'job_id':'job-0','attempt_id':attempt['id'],'version':1,'result_revision':1,'created_at':first['updated_at'],'system_id':'EMS','factory_id':'','context_id':'synthetic-retained-history'}
  message=self.server.chats['existing-chat']['chat']['history']['messages']['previous-user']
  message['meta']={'ees_work_reference':reference}
  later=self.command('save_inputs',run_id=run['id'],expected_revision=first['revision'],values={'note':'나중 입력'})['run']
  latest=self.command('human_confirm',run_id=run['id'],job_id='job-0',expected_revision=later['revision'])['run']
  self.assertEqual(len(latest['attempts']),2)
  self.navigate('/c/existing-chat')
  selector='#message-previous-user [data-ees-reference-slot] [data-action=open_reference]'
  self.wait('document.querySelector('+json.dumps(selector)+')')
  slot=self.browser.evaluate('document.querySelector("#message-previous-user [data-ees-reference-slot]").outerHTML')
  self.assertIn('기준 시각',self.text(selector));self.assertNotIn('기록 없음',self.text(selector))
  self.assertEqual(self.browser.evaluate('document.querySelectorAll("#message-previous-user .ees-work-message-reference [data-action=open_reference]").length'),0)
  self.click(selector)
  self.wait('document.querySelector("#ees-work-panel")?.innerText.includes("대화에서 참조한 과거 기록")')
  self.click('#ees-work-panel .ew-history summary')
  visible=self.text('#ees-work-panel')
  self.assertIn('첫 번째 입력',visible);self.assertNotIn('나중 입력',visible)
  self.assertFalse(self.browser.evaluate('!!document.querySelector("#ees-work-panel [data-mutation]")'))
  self.assertEqual(self.state(run_id=run['id'])['run'],latest)
  self.screenshot('source-reference-slot-old-attempt')
  Path('/tmp/phase2-reference-slot-probe.json').write_text(json.dumps({'scope':'actual built Native UI and real Work SQLite; synthetic Native session/chat storage and external transport','wheel_sha256':'1b9ffa24cfca97f2fa40f01652b01b918e3b19eadbb2f4856cf599d1dca35193','reference':reference,'slot_html':slot,'historical_panel':visible,'old_selector_count':0,'new_selector_count':1,'latest_attempts':2,'work_unchanged':True},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
unittest.main(verbosity=2)
