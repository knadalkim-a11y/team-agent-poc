"""Reconstructed runtime contracts after workspace loss; rerun evidence is separate.

The built Native frontend and production workflow service are real. Session,
external read results, and model responses are synthetic fixtures.
"""
import asyncio
from copy import deepcopy
from uuid import uuid4

from ees_work_integrated_fixture import IntegratedNativeCase


class SyntheticReviewModel:
    async def available(self, actor):
        return [{'id': 'synthetic-review', 'name': '합성 검토 모델'}]

    async def resolve(self, actor, model_id):
        if model_id != 'synthetic-review':
            raise AssertionError('The test never uses an in-house model')
        return {'id': model_id, 'name': '합성 검토 모델'}

    async def propose(self, actor, model_id, context, instruction):
        return {'ok': True, 'context': {key: context[key] for key in ('context_id', 'target_id', 'revision', 'kind')},
                'proposal': '합성 AI 원문: 아직 사람 확정과 송부가 없습니다.'}


class FigmaRuntimeNativeTests(IntegratedNativeCase):
    def execute(self, run, job='job-0'):
        result = asyncio.run(self.server.workflow.operations.command(self.server.user,
            {'action': 'execute_job', 'run_id': run['id'], 'job_id': job,
             'expected_revision': run['revision'], 'request_id': str(uuid4())}))
        self.assertTrue(result['ok'], result)
        return self.state(run_id=run['id'])['run']

    def test_pending_item_choices_survive_reload_before_atomic_confirmation(self):
        self.bridge.result = {'status': 'succeeded', 'completeness': 'complete', 'items': [
            {'id': 'ONE', 'name': '합성 항목 1', 'ai_suggestion': 'completed'},
            {'id': 'TWO', 'name': '합성 항목 2', 'required': False}]}
        key = self.author(mode='tool', block='item_verdict', jobs=1)
        run = self.execute(self.start(key)); self.open_run(key, run)
        self.assertTrue(self.read('[data-action=confirm_verdicts]', 'disabled'))
        self.choose('[data-item-verdict][data-item-id=ONE]', 'completed')
        self.assertTrue(self.read('[data-action=confirm_verdicts]', 'disabled'))
        self.choose('[data-item-verdict][data-item-id=TWO]', 'unknown')
        self.wait("!document.querySelector('[data-action=confirm_verdicts]')?.disabled")
        import time
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            drafts = self.state()['ui_state']['state'].get('selection', {}).get('verdict_drafts', {})
            if any(value.get('TWO', {}).get('verdict') == 'unknown' for value in drafts.values()):
                break
            time.sleep(.025)
        else:
            self.fail('Pending choices were not persisted before reload')
        self.assertEqual(self.state(run_id=run['id'])['run']['jobs']['job-0']['decisions'], [])
        self.navigate('/c/existing-chat'); self.wait("document.querySelector('[data-item-verdict][data-item-id=TWO]')?.value==='unknown'")
        self.assertEqual(self.read('[data-item-verdict][data-item-id=ONE]', 'value'), 'completed')
        self.click('[data-action=confirm_verdicts]'); self.click('[data-dialog-confirm]')
        self.wait("document.querySelector('.ew-result-items')?.innerText.includes('모든 항목의 판정이 확정')")
        saved = self.state(run_id=run['id'])['run']['jobs']['job-0']
        self.assertEqual({d['item_id']: d['verdict'] for d in saved['decisions']}, {'ONE': 'completed', 'TWO': 'unknown'})
        self.assertEqual(self.browser.evaluate("document.querySelectorAll('.ew-confirmed-verdict').length"), 2)
        self.screenshot('figma-r3-pending-and-final-verdicts')

    def test_checklist_criterion_and_tool_evidence_are_distinct_in_native_panel(self):
        self.bridge.result = {'status': 'succeeded', 'completeness': 'complete', 'items': [
            {'id': 'QUEUE', 'name': '대기열 감소', 'status': 'failed', 'criterion': '조회한 대기열이 감소함',
             'evidence': [{'name': '합성 대기열 조회', 'tool_id': 'synthetic-read', 'status': 'succeeded',
                           'action': '현재 대기열 조회', 'success_criterion': '응답에 건수 포함', 'result': '100 → 120'}]}]}
        key = self.author(mode='tool', block='checklist', jobs=1)
        run = self.execute(self.start(key)); self.open_run(key, run)
        self.assertEqual(self.read('.ew-check-item > .ew-status', 'dataset.status'), 'failed')
        self.assertEqual(self.read('.ew-check-evidence .ew-status', 'dataset.status'), 'succeeded')
        self.click('.ew-check-evidence summary')
        self.assertIn('통과 기준 · 조회한 대기열이 감소함', self.text('.ew-check-item'))
        self.assertIn('정상 실행 기준 · 응답에 건수 포함', self.text('.ew-check-evidence'))
        self.assertIn('100 → 120', self.text('.ew-check-evidence'))
        self.assertEqual(self.state(run_id=run['id'])['run']['jobs']['job-0']['decisions'], [])
        self.screenshot('figma-s3-checklist-criterion-versus-tool')

    def test_ees_schema_typed_values_and_reason_stay_separate_before_blocked_dispatch(self):
        reference = {'tool_id': 'synthetic-ees', 'function': 'restart', 'revision': 1, 'content_hash': 'a' * 64, 'schema_hash': 'b' * 64}
        schema = {'type': 'object', 'properties': {'target': {'type': 'string', 'title': '대상 서버'},
            'stop': {'type': 'string', 'title': '종료 방식', 'enum': ['graceful', 'force']},
            'wait': {'type': 'integer', 'title': '종료 대기', 'minimum': 0, 'maximum': 300}}, 'required': ['target', 'stop', 'wait']}
        async def inspect(actor, tool_id, function):
            return {'reference': {**reference, 'function': function}, 'schema': deepcopy(schema)}
        self.bridge.inspect_registered = inspect
        self.users['other-user']['role'] = 'admin'
        def operation(action, revision=0, user=None, **kwargs):
            result = asyncio.run(self.server.workflow.operations.command(user or self.server.user,
                dict(action=action, expected_revision=revision, request_id=str(uuid4()), **kwargs)))
            self.assertTrue(result['ok'], result); return result
        tool = operation('tool_save', tool={'system_id': 'EMS', 'kind': 'request', 'name': '합성 재시작',
            'reference': reference, 'guide_url': 'https://example.invalid/guide', 'responsible_user_id': 'other-user',
            'status_function': 'status', 'output_schema': {'type': 'object'}})['tool']
        tool = operation('tool_submit', tool['revision'], tool_contract_id=tool['id'])['tool']
        tool = operation('tool_review', tool['revision'], user=self.users['other-user'], tool_contract_id=tool['id'], decision='approve')['tool']
        key = self.author(jobs=1, fields=[{'id': 'target', 'name': '대상', 'type': 'text', 'scope': 'run'},
            {'id': 'stop', 'type': 'single', 'scope': 'run', 'options': ['graceful', 'force']},
            {'id': 'wait', 'type': 'number', 'scope': 'run'}])
        draft = deepcopy(self.state(workflow_id=key)['workflow']['draft'])
        draft['nodes']['job-0'].update(result_block='change_request', tool_contract_id=tool['id'], tool_contract_revision=tool['revision'],
            approval_count=0, effect_criterion={'check': 'registered-status'})
        self.command('save_draft', workflow_id=key, expected_revision=3, definition=draft)
        self.command('validate_workflow', workflow_id=key, expected_revision=4)
        self.command('publish_workflow', workflow_id=key, expected_revision=4)
        run = self.start(key, inputs={'target': 'SYNTHETIC-AP', 'stop': 'graceful', 'wait': 60}); self.open_run(key, run)
        self.assertEqual(self.read('[data-work-input][name=wait]', 'type'), 'number')
        self.assertEqual(self.read('[data-work-input][name=wait]', 'max'), '300')
        self.assertEqual(self.read('[data-work-input][name=stop]', 'tagName'), 'SELECT')
        self.fill('#ees-request-reason', '합성 확인 사유')
        self.click('[data-action=request_intent]')
        self.wait("document.querySelector('#ees-work-dialog')?.innerText.includes('합성 확인 사유')")
        self.assertIn('SYNTHETIC-AP', self.text('#ees-work-dialog'))
        self.click('[data-dialog-confirm]')
        self.wait("document.querySelector('#ees-work-panel')?.innerText.includes('연결')")
        with self.server.workflow._db() as db:
            import json
            request = json.loads(db.execute('SELECT data FROM work_external_requests WHERE run_id=?', (run['id'],)).fetchone()[0])
        self.assertEqual(request['inputs'], {'target': 'SYNTHETIC-AP', 'stop': 'graceful', 'wait': 60})
        self.assertEqual(request['request_reason'], '합성 확인 사유')
        self.assertNotEqual(request['state'], 'effect_verified')
        self.assertEqual(self.bridge.calls, [])
        self.screenshot('figma-a4-typed-request-unconnected')

    def test_list_preview_add_exclude_confirm_and_history_preserve_original(self):
        self.bridge.result = {'status': 'succeeded', 'completeness': 'complete',
            'items': [{'id': 'CR-1', 'title': '합성 조회 1', 'status': '검증 완료'},
                      {'id': 'CR-2', 'title': '합성 조회 2', 'status': '대기'}],
            'suggestions': [{'id': 'CR-3', 'title': '합성 후보', 'reason': '담당자 확인 필요'}]}
        key = self.author(mode='tool', block='list_confirm', jobs=1)
        run = self.execute(self.start(key)); original = deepcopy(run['attempts'][0])
        self.open_run(key, run)
        self.click('[data-action=overview]')
        self.assertEqual(self.browser.evaluate("document.querySelectorAll('.ew-phase-overview').length"), 1)
        self.wait("[...document.querySelectorAll('.ew-job-actor img')].every(image => image.complete && image.naturalWidth > 0)")
        self.screenshot('figma-a5-cycle-overview')
        self.click('[data-action=job][data-job-id=job-0]')
        self.assertFalse(self.read('[data-list-include][data-item-id="CR-3"]', 'checked'))
        self.click('[data-list-include][data-item-id="CR-2"]')
        self.assertEqual(self.browser.evaluate('document.activeElement?.dataset.itemId'), 'CR-2')
        self.click('[data-list-include][data-item-id="CR-3"]')
        self.click('[data-action="add_list_item"]')
        self.fill('#ees-list-add-id', 'CR-4'); self.fill('#ees-list-add-name', '사람이 추가한 합성 항목')
        self.click('[data-dialog-confirm]')
        self.assertEqual(self.state(run_id=run['id'])['run']['jobs']['job-0']['decisions'], [])
        self.assertEqual(len(self.state(run_id=run['id'])['run']['attempts']), 1)
        self.click('[data-action="confirm_list"]')
        self.fill('#ees-list-confirm-reason', '후보와 제외 사유를 합성 담당자가 직접 확인')
        self.click('[data-dialog-confirm]')
        self.wait("document.querySelector('.ew-list-confirm')?.innerText.includes('사람 확정 기록 있음')")
        saved = self.state(run_id=run['id'])['run']; current = saved['attempts'][-1]
        self.assertEqual(saved['attempts'][0]['result'], original['result'])
        self.assertEqual(len(saved['attempts']), 2)
        self.assertEqual({item['item_id'] for item in saved['jobs']['job-0']['decisions']}, {'CR-1', 'CR-3', 'CR-4'})
        self.assertFalse(next(item for item in current['result']['items'] if item['id'] == 'CR-2')['selected'])
        self.assertEqual(next(item for item in current['result']['items'] if item['id'] == 'CR-4')['source']['kind'], 'human_added')
        self.assertEqual(len(self.bridge.calls), 1)
        self.assertIn('조회 2건', self.text('.ew-list-confirm'))
        self.assertIn('포함 3 · 추가 2 · 제외 1', self.text('.ew-list-toolbar'))
        self.assertEqual(self.text('.ew-list-confirm').count('사람이 추가 · 원본 조회 확인 전'), 2)
        self.screenshot('figma-a6-list-confirmed')
        # A zero-row lookup is a result. Completion policy remains unresolved.
        self.bridge.result = {'status': 'succeeded', 'completeness': 'complete', 'items': []}
        empty_key = self.author(mode='tool', block='list_confirm', jobs=1, name='합성 빈 목록')
        empty_run = self.execute(self.start(empty_key)); self.open_run(empty_key, empty_run)
        self.assertIn('조회 0건', self.text('.ew-list-confirm'))
        self.assertTrue(self.read('[data-action="confirm_list"]', 'disabled'))
        self.click('[data-action="save_list_selection"]')
        self.fill('#ees-list-confirm-reason', '조회 0건이며 완료 정책은 미정')
        self.click('[data-dialog-confirm]')
        self.wait("window.__eesNativeWorkV1.captureReference()?.result_revision === 2 && document.querySelector('.ew-list-confirm')?.innerText.includes('조회 0건')")
        empty_saved = self.state(run_id=empty_run['id'])['run']
        self.assertEqual(len(empty_saved['attempts']), 2)
        self.assertEqual(empty_saved['jobs']['job-0']['decisions'], [])
        self.assertTrue(self.read('[data-action="confirm_list"]', 'disabled'))
        self.click('[data-action="add_list_item"]')
        self.fill('#ees-list-add-id', 'MANUAL-1'); self.fill('#ees-list-add-name', '조회 0건 후 사람이 준비')
        self.click('[data-dialog-confirm]')
        self.wait("document.querySelector('[data-list-include][data-item-id=\"MANUAL-1\"]')?.checked === true")
        self.assertIn('MANUAL-1', self.text('.ew-list-confirm'))
        self.assertEqual(self.state(run_id=empty_run['id'])['run']['revision'], empty_saved['revision'])
        self.screenshot('figma-a6-empty-lookup-manual-preview')

    def test_ai_review_autosaves_without_sending_and_confirmation_freezes_text(self):
        self.server.workflow.operations.model = SyntheticReviewModel()
        key = self.author(mode='ai', block='ai_review', jobs=1)
        run = self.start(key); self.open_run(key, run)
        self.click('[data-action="execute"]')
        self.wait("document.querySelector('#ees-review-text')?.value.includes('합성 AI 원문')")
        first = self.state(run_id=run['id'])['run']; original = deepcopy(first['attempts'][0]['result'])
        self.fill('#ees-review-text', '사람이 보완한 검토 본문 · 실제 송부 아님')
        self.wait("document.querySelector('#ees-review-text')?.dataset.reviewRevision === '1'")
        saved = self.state(run_id=run['id'])['run']
        self.assertEqual(saved['jobs']['job-0']['review_draft']['text'], '사람이 보완한 검토 본문 · 실제 송부 아님')
        self.assertEqual(saved['attempts'][0]['result'], original)
        self.assertEqual(saved['jobs']['job-0']['decisions'], [])
        self.assertFalse(self.browser.evaluate("!!document.querySelector('[data-action=send_review_draft]')"))
        self.screenshot('figma-review-purpose-saved')
        self.click('[data-action=confirm]'); self.click('[data-dialog-confirm]')
        self.refresh()
        self.wait("document.querySelector('#ees-review-text')?.readOnly")
        self.assertFalse(self.browser.evaluate("!!document.querySelector('[data-action=save_review_draft]')"))
        final = self.state(run_id=run['id'])['run']
        self.assertEqual(final['attempts'][0]['result'], original)
        self.assertTrue(final['attempts'][0]['review_history'][-1]['decision_id'])

    def test_delivery_purpose_review_is_recorded_but_completion_remains_blocked(self):
        self.server.workflow.operations.model = SyntheticReviewModel()
        key = self.author(mode='ai', block='ai_review', jobs=1)
        draft = deepcopy(self.state(workflow_id=key)['workflow']['draft'])
        draft['nodes']['job-0']['completion'] = {'kind': 'delivery'}
        self.command('save_draft', workflow_id=key, expected_revision=3, definition=draft)
        self.command('validate_workflow', workflow_id=key, expected_revision=4)
        self.command('publish_workflow', workflow_id=key, expected_revision=4)
        run = self.start(key); self.open_run(key, run)
        self.click('[data-action="execute"]')
        self.wait("document.querySelector('#ees-review-text')?.value.includes('합성 AI 원문')")
        original = deepcopy(self.state(run_id=run['id'])['run']['attempts'][0]['result'])
        self.fill('#ees-review-text', '송부 전 검토한 합성 본문')
        self.wait("document.querySelector('#ees-review-text')?.dataset.reviewRevision === '1'")
        self.assertTrue(self.read('[data-action="send_review_draft"]', 'disabled'))
        self.click('[data-action=confirm]')
        self.assertIn('송부하거나 업무를 완료하지 않습니다', self.text('#ees-work-dialog'))
        self.click('[data-dialog-confirm]')
        self.wait("document.querySelector('#ees-review-text')?.readOnly")
        saved = self.state(run_id=run['id'])['run']
        self.assertEqual(saved['jobs']['job-0']['status'], 'blocked')
        self.assertEqual(saved['jobs']['job-0']['reason'], 'delivery_unconfigured')
        self.assertEqual(saved['attempts'][0]['result'], original)
        self.assertTrue(saved['attempts'][0]['review_history'][-1]['decision_id'])
        self.assertTrue(self.read('[data-action="send_review_draft"]', 'disabled'))
        self.click('[data-action=overview]'); self.click('[data-action=close_run]')
        self.click('[data-dialog-confirm]')
        self.wait("document.querySelector('.ew-error')?.innerText.includes('필수 작업')")
        self.assertEqual(self.state(run_id=run['id'])['run']['status'], 'open')
        self.assertIn('송부 연결 필요', self.text('.ew-phase-job'))
        self.assertNotIn('delivery_unconfigured', self.text('.ew-phase-job'))
        self.screenshot('figma-a7-delivery-review-blocked')

    def test_closed_record_uses_old_shared_values_and_asking_only_changes_reference(self):
        key = self.author(jobs=1, fields=[{'id': 'setting', 'name': '조회 설정', 'type': 'text', 'scope': 'workflow'}])
        self.command('save_settings', workflow_id=key, values={'setting': '당시 값'})
        run = self.start(key)
        run = self.command('human_confirm', run_id=run['id'], job_id='job-0', expected_revision=run['revision'])['run']
        run = self.command('close_run', run_id=run['id'], expected_revision=run['revision'])['run']
        self.command('save_settings', workflow_id=key, expected_revision=1, values={'setting': '현재 값'})
        self.refresh(); self.click('[data-action="records"]')
        self.click('[data-action="open_run"][data-run-id="' + run['id'] + '"]')
        self.click('[data-action="workflow_records"]')
        self.assertTrue(self.browser.evaluate("!!document.querySelector('.ew-record-filter')"))
        self.click('[data-action="open_run"][data-run-id="' + run['id'] + '"]')
        self.click('.ew-history summary')
        self.assertIn('당시 값', self.text('.ew-history-values'))
        self.assertIn('지금과 다름', self.text('.ew-history-values'))
        self.assertNotIn('현재 값', self.text('.ew-history-values'))
        before = self.state(run_id=run['id'])['run']
        self.click('.ew-history [data-action="ask_record"]')
        reference = self.browser.evaluate('window.__eesNativeWorkV1.captureReference()')
        self.assertEqual(reference['attempt_id'], before['attempts'][0]['id'])
        self.assertTrue(self.read('.ew-history', 'open'))
        self.assertIn('당시 값', self.text('.ew-history-values'))
        self.assertEqual(self.browser.evaluate('document.activeElement?.id'), 'chat-input')
        after = self.state(run_id=run['id'])['run']
        self.assertEqual(before['revision'], after['revision']); self.assertEqual(before['attempts'], after['attempts'])
        self.assertEqual(self.bridge.calls, [])
        self.screenshot('figma-s2-readonly-history-reference')

    def test_assigned_human_task_exposes_readonly_inputs_and_no_mutation_button(self):
        self.command('save_access', principal_kind='user', principal_id='other-user', system_id='EMS', factory_id='*', roles=['participant'])
        key = self.author(jobs=1, fields=[{'id': 'note', 'name': '메모', 'type': 'text', 'scope': 'run'}])
        draft = deepcopy(self.state(workflow_id=key)['workflow']['draft'])
        draft['nodes']['job-0']['assignee'] = {'kind': 'user', 'id': 'other-user'}
        self.command('save_draft', workflow_id=key, expected_revision=3, definition=draft)
        self.command('validate_workflow', workflow_id=key, expected_revision=4)
        self.command('publish_workflow', workflow_id=key, expected_revision=4)
        run = self.start(key, inputs={'note': '합성 공유 입력'}); self.open_run(key, run)
        self.assertTrue(self.read('[data-work-input][name="note"]', 'disabled'))
        self.assertFalse(self.browser.evaluate("!!document.querySelector('[data-action=confirm],[data-action=save_inputs],[data-action=execute]')"))
        self.assertIn('배정된 담당자 · Other synthetic user', self.text('#ees-work-panel'))
        self.assertEqual(self.state(run_id=run['id'])['run']['attempts'], [])
        self.screenshot('figma-s1-human-permission-readonly')
