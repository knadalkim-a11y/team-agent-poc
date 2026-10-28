"""Reconstructed runtime contracts after workspace loss; rerun evidence is separate.

The built Native frontend and production workflow service are real. Session,
external read results, and model responses are synthetic fixtures.
"""
import asyncio
from copy import deepcopy
import importlib
import json
from pathlib import Path
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
    def operations_stage(self):
        """Approved layout data authored only in this test's temporary database."""
        async def assets(actor):
            return {'available': True, 'skills': [{'id': 'synthetic-document-guide'}],
                'skill_bodies': {'synthetic-document-guide': '합성 지침: 반환된 문서 목록과 접근 결과를 기록합니다.'},
                'skill_versions': {'synthetic-document-guide': 1}}
        self.server.workflow._assets = assets
        created = self.command('create_workflow', name='배포 산출물 점검', system_id='EMS')
        key, definition = created['workflow_id'], created['workflow']['draft']
        root = next(iter(definition['nodes']))
        definition['nodes'][root]['children'] = ['stage']
        names = ['로그인 화면 문구 수정', '알람 기준값 조정', '보고서 출력 양식 변경', '대시보드 필터 추가',
            '설비 목록 정렬 수정', '데이터 보관 기간 변경', '배치 주기 조정', '메일 발송 대상 추가',
            '화면 응답 속도 개선', '권한 그룹 정리', '이력 조회 기간 확대', '오류 메시지 정리']
        definition['nodes']['stage'] = {'id': 'stage', 'type': 't', 'name': '1차 점검', 'parent': root,
            'children': ['job-' + str(index) for index in range(len(names))], 'deps': []}
        judgments = [{'id': 'approved', 'label': '승인', 'status': 'completed'},
            {'id': 'conditional', 'label': '조건부 승인', 'status': 'completed'},
            {'id': 'rejected', 'label': '미승인', 'status': 'failed'}]
        for index, name in enumerate(names):
            human = index in (2, 6, 9)
            job_id = 'job-' + str(index)
            node = {'id': job_id, 'type': 'j', 'name': name, 'parent': 'stage', 'children': [], 'deps': [],
                'mode': 'human' if human else 'tool', 'result_block': 'human_confirm' if human else 'values',
                'human_confirmation': human, 'inputs': [], 'instructions': '반환된 자료를 확인한 실행 기록입니다.'}
            if human:
                # The conditional meaning is explicit in this synthetic definition,
                # never a new product-wide approval/completion policy.
                node['judgments'] = deepcopy(judgments)
            else:
                node.update(inputs=[{'id': 'query', 'name': '조회 조건', 'type': 'text', 'scope': 'run'}],
                    argument_bindings={'query': {'input': 'query'}}, skills=['synthetic-document-guide'],
                    tool_reference={'tool_id': 'synthetic-read', 'function': 'read', 'revision': 1,
                        'content_hash': 'a' * 64, 'schema_hash': 'b' * 64})
            definition['nodes'][job_id] = node
        self.command('save_draft', workflow_id=key, expected_revision=1, definition=definition)
        checked = self.command('validate_workflow', workflow_id=key, expected_revision=2)
        self.assertEqual(checked['validation']['errors'], [], checked)
        self.command('publish_workflow', workflow_id=key, expected_revision=2)
        run = self.start(key, inputs={'query': '이번 배포 문서'})
        for index in (0, 1, 3, 4, 5, 7, 8):
            self.bridge.result = {'status': 'failed' if index == 3 else 'succeeded', 'completeness': 'complete',
                'items': [{'id': 'internal-one', 'name': '작업 결과 내부 문서 1'},
                    {'id': 'internal-two', 'name': '작업 결과 내부 문서 2'}],
                'data': {'summary': '합성 원본 실행 ' + str(index)}}
            result = asyncio.run(self.server.workflow.operations.command(self.server.user, {
                'action': 'execute_job', 'run_id': run['id'], 'job_id': 'job-' + str(index),
                'expected_revision': run['revision'], 'request_id': str(uuid4())}))
            self.assertEqual(result['ok'], index != 3, result)
            self.assertEqual(result['attempt']['status'], 'failed' if index == 3 else 'succeeded')
            run = self.state(run_id=run['id'])['run']
        return key, run

    def stage_capture(self, label):
        self.wait("!document.querySelector('[data-ees-motion=opening],[data-ees-motion=closing]')")
        observed = self.browser.evaluate("""(() => {
            const panel=document.querySelector('#ees-work-panel'), rect=e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};};
            const styled=e=>{const s=getComputedStyle(e);return {...rect(e),fontSize:s.fontSize,lineHeight:s.lineHeight,background:s.backgroundColor,border:s.borderWidth};};
            return {viewport:{width:innerWidth,height:innerHeight},panel:rect(panel),overflow:panel.scrollWidth-panel.clientWidth,
                header:styled(panel.querySelector('.ew-panel-header')),title:styled(panel.querySelector('h2')),
                rows:[...panel.querySelectorAll('[data-stage-job]')].map(e=>({job:e.dataset.stageJob,...rect(e)})),
                menu:panel.querySelector('#ees-stage-verdict-menu')?styled(panel.querySelector('#ees-stage-verdict-menu')):null,
                controls:[...panel.querySelectorAll('.ew-vd-pick,.ew-vd-run,.ew-vd-evidence-toggle')].filter(e=>e.getClientRects().length).map(e=>({text:e.innerText,...styled(e)}))};
        })()""")
        self.assertLessEqual(observed['overflow'], 1, observed)
        self.assertAlmostEqual(observed['header']['height'], 48, delta=1, msg=observed)
        self.assertEqual(observed['title']['fontSize'], '20px', observed)
        self.assertEqual(observed['title']['lineHeight'], '28px', observed)
        if observed['menu']:
            self.assertAlmostEqual(observed['menu']['width'], 180, delta=1, msg=observed)
            self.assertAlmostEqual(observed['menu']['height'], 110, delta=1, msg=observed)
            self.assertGreaterEqual(observed['menu']['x'], observed['panel']['x'] + 7, observed)
            self.assertLessEqual(observed['menu']['x'] + observed['menu']['width'], observed['panel']['x'] + observed['panel']['width'] - 7, observed)
        directory = self.screenshot(label)
        (directory / (label + '.json')).write_text(json.dumps(observed, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def test_operations_stage_actual_jobs_header_and_judgment_menu_at_two_widths(self):
        key, run = self.operations_stage()
        self.browser.call('Emulation.setDeviceMetricsOverride', {'width': 1920, 'height': 1080, 'deviceScaleFactor': 1, 'mobile': False})
        self.open_run(key, run, job='')
        self.wait("document.querySelector('#ees-work-panel.ew-vd h2')?.textContent === '1차 점검'")
        self.assertEqual(self.text('.ew-run-back'), '배포 산출물 점검')
        self.assertIn('작업 12개', self.text('.ew-vd-head'))
        self.assertNotIn('회차', self.text('.ew-run-nav') + self.text('.ew-vd-head'))
        self.assertNotIn('자동실행 예약 없음', self.text('.ew-vd-head'))
        self.assertNotIn('업무절차 · 수시 · 직접 시작', self.text('.ew-vd-head'))
        self.assertFalse(self.browser.evaluate("!!document.querySelector('[data-stage-job=internal-one],[data-stage-job=internal-two]')"))
        self.assertEqual(self.read('[data-task-group=waiting] .ew-vd-label'), '대기5')
        self.assertEqual(self.text('[data-stage-job=job-3] [data-decision-status]'), '실행 실패')
        self.assertEqual(self.text('[data-stage-job=job-0] [data-decision-status]'), '실행 완료')
        self.assertFalse(self.browser.evaluate("!!document.querySelector('[data-stage-job=job-0] [data-action=stage_verdict]')"))
        self.stage_capture('operations-stage-default-1920')
        self.click('[data-action=stage_approved]')
        self.assertEqual(self.browser.evaluate("[...document.querySelectorAll('[data-stage-job]')].map(e=>e.dataset.stageJob).sort()"), sorted(run['jobs']))
        self.click('[data-action=stage_approved]')
        for width in (1920, 480):
            self.browser.call('Emulation.setDeviceMetricsOverride', {'width': width, 'height': 1080, 'deviceScaleFactor': 1, 'mobile': False})
            self.wait('innerWidth === ' + str(width))
            self.click('[data-action=stage_verdict][data-job-id=job-2]')
            self.wait("document.querySelector('#ees-stage-verdict-menu [role=menuitemradio]')")
            self.assertEqual(self.browser.evaluate("[...document.querySelectorAll('#ees-stage-verdict-menu b')].map(e=>e.textContent)"), ['승인', '조건부 승인', '미승인'])
            self.stage_capture('operations-stage-menu-' + str(width))
            self.key('Escape', 27)
            self.wait("!document.querySelector('#ees-stage-verdict-menu')")
            self.assertEqual(self.browser.evaluate('document.activeElement.dataset.action'), 'stage_verdict')
        self.click('[data-action=stage_verdict][data-job-id=job-2]')
        self.click('[data-action=stage_decide][data-judgment-id=approved]')
        self.wait("document.querySelector('[data-action=stage_verdict][data-job-id=job-2]')?.innerText.includes('승인')")
        first = deepcopy(self.state(run_id=run['id'])['run'])
        first_decision = first['jobs']['job-2']['decisions'][0]
        self.assertEqual(first_decision['verdict'], 'completed')
        self.assertTrue(first_decision['note'].endswith('선택한 판정: 승인 (approved)'))
        self.click('[data-action=stage_verdict][data-job-id=job-2]')
        self.assertEqual(self.read('[data-action=stage_decide][data-judgment-id=approved]', "getAttribute('aria-checked')"), 'true')
        self.stage_capture('operations-stage-selected-menu-480')
        self.key('ArrowDown', 40); self.key('Enter', 13)
        self.wait("document.querySelector('[data-action=stage_verdict][data-job-id=job-2]')?.innerText.includes('조건부 승인')")
        second = self.state(run_id=run['id'])['run']
        self.assertEqual([d for d in second['jobs']['job-2']['decisions'] if d['id'] == first_decision['id']], [first_decision])
        self.assertEqual(len([a for a in second['attempts'] if a['job_id'] == 'job-2']), 2)
        self.assertEqual(len(second['jobs']['job-2']['decisions']), 2)
        self.click('[data-action=stage_evidence][data-job-id=job-2]')
        self.assertIn('조건부 승인', self.text('#stage-evidence-job-2'))
        self.assertEqual(self.browser.evaluate("[...document.querySelectorAll('#stage-evidence-job-2 [data-human-selection] b')].map(e=>e.textContent)"), ['조건부 승인', '승인'])
        self.stage_capture('operations-stage-human-record-480')
        for tab in ('log', 'rules'):
            self.click('[data-action=stage_tab][data-tab=' + tab + ']')
            self.wait("document.querySelector('[data-action=stage_tab][data-tab=" + tab + "][aria-pressed=true]')")
            self.stage_capture('operations-stage-' + tab + '-480')
        self.assertIn('조건부 승인', self.text('.ew-vd-rules'))

    def test_operations_stage_actual_tool_evidence_retry_and_scope_execution(self):
        key, run = self.operations_stage()
        self.browser.call('Emulation.setDeviceMetricsOverride', {'width': 1920, 'height': 1080, 'deviceScaleFactor': 1, 'mobile': False})
        self.open_run(key, run, job='')
        self.wait("document.querySelector('#ees-work-panel.ew-vd')")
        original = deepcopy(next(a for a in run['attempts'] if a['job_id'] == 'job-3'))
        self.click('[data-action=stage_evidence][data-job-id=job-3]')
        self.click('[data-action=stage_tool][data-job-id=job-3]')
        detail = self.text('#stage-tool-job-3')
        for expected in ('이번 배포 문서', '합성 원본 실행 3', '합성 지침: 반환된 문서 목록과 접근 결과를 기록합니다.', '실행 실패'):
            self.assertIn(expected, detail)
        self.assertNotIn('미승인', detail)
        self.stage_capture('operations-stage-tool-detail-1920')
        writes, calls = len(self.server.workspace_commands), len(self.bridge.calls)
        self.bridge.result = {'status': 'succeeded', 'completeness': 'complete', 'data': {'summary': '합성 두 번째 실행 결과'}}
        self.bridge.hold.clear(); self.bridge.started.clear()
        self.click('[data-action=stage_execute][data-job-id=job-3]')
        self.assertTrue(self.bridge.started.wait(5))
        self.refresh()
        self.wait("document.querySelector('[data-stage-job=job-3] [data-decision-status]')?.innerText === '실행 중'")
        self.stage_capture('operations-stage-tool-running-1920')
        self.bridge.hold.set()
        self.wait("document.querySelector('[data-stage-job=job-3] [data-decision-status]')?.innerText === '실행 완료'")
        business = [body for body in self.server.workspace_commands[writes:] if body.get('action') != 'save_ui']
        self.assertEqual([(b['action'], b.get('job_id')) for b in business], [('execute_job', 'job-3')])
        self.assertEqual([entry['context']['job_id'] for entry in self.bridge.calls[calls:]], ['job-3'])
        after = self.state(run_id=run['id'])['run']
        attempts = [a for a in after['attempts'] if a['job_id'] == 'job-3']
        self.assertEqual(len(attempts), 2)
        self.assertEqual(next(a for a in attempts if a['id'] == original['id']), original)
        if not self.browser.evaluate("!!document.querySelector('#stage-evidence-job-3')"):
            self.click('[data-action=stage_evidence][data-job-id=job-3]')
        self.wait("document.querySelector('[data-stage-attempt][data-job-id=job-3]')")
        self.choose('[data-stage-attempt][data-job-id=job-3]', original['id'])
        self.wait("document.querySelector('#stage-evidence-job-3 .ew-attempt-caption')?.innerText.includes('이전 실행 결과')")
        self.click('[data-action=stage_tool][data-job-id=job-3]')
        self.assertIn('합성 원본 실행 3', self.text('#stage-tool-job-3'))
        self.assertNotIn('합성 두 번째 실행 결과', self.text('#stage-tool-job-3'))
        self.stage_capture('operations-stage-prior-tool-1920')
        self.browser.call('Emulation.setDeviceMetricsOverride', {'width': 480, 'height': 1080, 'deviceScaleFactor': 1, 'mobile': False})
        self.wait('innerWidth === 480')
        self.stage_capture('operations-stage-prior-tool-480')
        self.browser.call('Emulation.setDeviceMetricsOverride', {'width': 1920, 'height': 1080, 'deviceScaleFactor': 1, 'mobile': False})
        self.wait('innerWidth === 1920')
        writes, calls = len(self.server.workspace_commands), len(self.bridge.calls)
        self.click('[data-action=execute_scope][data-node-id=stage]')
        self.wait("!document.querySelector('#ees-work-panel[aria-busy=true]')")
        business = [body for body in self.server.workspace_commands[writes:] if body.get('action') != 'save_ui']
        self.assertEqual([(b['action'], b.get('node_id')) for b in business], [('execute_scope', 'stage')])
        for _ in range(3):
            asyncio.run(self.server.workflow.operations.process_once())
        self.assertEqual([entry['context']['job_id'] for entry in self.bridge.calls[calls:]], ['job-10', 'job-11'])
        final = self.state(run_id=run['id'])['run']
        self.assertEqual(len([a for a in final['attempts'] if a['job_id'] == 'job-0']), 1)
        self.assertEqual(final['jobs']['job-2']['decisions'], [])
        self.refresh()
        self.stage_capture('operations-stage-executed-1920')

    def preview_inputs(self, run, values, job='job-0'):
        reference = self.browser.evaluate('window.__eesNativeWorkV1.captureReference()')
        payload = {'proposal_kind': 'inputs', 'workflow_id': run['workflow_id'], 'run_id': run['id'], 'job_id': job,
            'base_revision': run['revision'], 'context_id': reference['context_id'], 'proposal': values}
        result = self.browser.evaluate("window.__eesNativeWorkV1.propose('existing-chat'," + json.dumps(payload, ensure_ascii=False) + ")")
        self.assertTrue(result['ok'], result)
        self.wait("document.querySelector('.ew-input-proposal-bar [data-action=apply_input_proposal]')")

    def input_tabs_roundtrip(self):
        self.click('[data-action=tab][data-tab=history]')
        self.wait("document.querySelector('[data-action=tab][data-tab=history][aria-pressed=true]')")
        self.click('[data-action=tab][data-tab=current]')
        self.wait("document.querySelector('[data-action=tab][data-tab=current][aria-pressed=true]')")

    def assert_only_selection_remembered(self, start):
        # Tab changes legitimately persist private navigation after 400 ms.
        # Every business mutation remains forbidden, including input saves.
        for body in self.server.workspace_commands[start:]:
            self.assertEqual(body.get('action'), 'save_ui', body)
            self.assertEqual(set(body), {'action', 'expected_revision', 'request_id', 'state'}, body)
            self.assertEqual(set(body['state']), {'selection'}, body)
            self.assertIsInstance(body['state']['selection'], dict, body)

    def applied_inputs_evidence(self, hint, fields, label):
        self.assertEqual(self.text('.ew-input-proposal-applied'), '저장 전')
        self.assertEqual(self.text('.ew-input-applied-bar > p'), hint)
        self.assertEqual(self.text('.ew-input-applied-bar [data-action=discard_inputs]'), '최신 값으로 돌아가기')
        self.assertEqual(self.text('.ew-input-applied-bar [data-action=save_inputs]'), '입력 저장')
        self.assertEqual(self.browser.evaluate("[...document.querySelectorAll('#ees-work-inputs .ew-input-proposal-source')].map(e=>e.textContent)"), ['도우미'] * fields)
        self.browser.evaluate("document.querySelector('.ew-input-proposal-applied').scrollIntoView({block:'center',inline:'nearest'})")
        observed = self.browser.evaluate("""(() => {
            const panel=document.querySelector('#ees-work-panel'),bar=document.querySelector('.ew-input-applied-bar'),badge=document.querySelector('.ew-input-proposal-applied'),hint=bar.querySelector('p'),hintStyle=getComputedStyle(hint);
            const box=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height,color:s.color,background:s.backgroundColor};};
            return {width:innerWidth,bar:{...box(bar),gap:getComputedStyle(bar).gap},badge:box(badge),
                hint:{...box(hint),text:hint.textContent,wordBreak:hintStyle.wordBreak,overflowWrap:hintStyle.overflowWrap,fontSize:hintStyle.fontSize,lineHeight:hintStyle.lineHeight},
                buttons:[...bar.querySelectorAll('button')].map(e=>({text:e.textContent,...box(e)})),overflow:panel.scrollWidth-panel.clientWidth};
        })()""")
        self.assertLessEqual(observed['overflow'], 1, observed)
        self.assertEqual(observed['bar']['background'], 'rgb(255, 255, 255)', observed)
        self.assertEqual(observed['bar']['gap'], '10px', observed)
        self.assertEqual(observed['hint']['wordBreak'], 'keep-all', observed)
        self.assertEqual(observed['hint']['overflowWrap'], 'normal', observed)
        self.assertEqual(observed['hint']['color'], 'rgb(92, 94, 101)', observed)
        self.assertEqual(observed['hint']['fontSize'], '12px', observed)
        self.assertEqual(observed['hint']['lineHeight'], '18px', observed)
        self.assertGreater(observed['badge']['height'], 0, observed)
        self.assertGreaterEqual(observed['badge']['top'], 0, observed)
        self.assertLessEqual(observed['badge']['bottom'], observed['bar']['top'], observed)
        self.assertNotIn(observed['badge']['background'], ('rgba(0, 0, 0, 0)', 'transparent'), observed)
        for button in observed['buttons']:
            self.assertAlmostEqual(button['height'], 34, delta=1, msg=observed)
            self.assertGreaterEqual(button['left'], observed['bar']['left'] - 1, observed)
            self.assertLessEqual(button['right'], observed['bar']['right'] + 1, observed)
            self.assertGreaterEqual(button['top'], observed['bar']['top'] - 1, observed)
            self.assertLessEqual(button['bottom'], observed['bar']['bottom'] + 1, observed)
        self.wait("!document.querySelector('[data-ees-motion=opening],[data-ees-motion=closing]')")
        directory = self.screenshot(label)
        (directory / (label + '.json')).write_text(json.dumps(observed, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def test_e2_input_proposal_tabs_discard_scope_and_a4a_at_480_and_1366(self):
        fields = [{'id': 'note', 'name': '자료 메모', 'type': 'text', 'scope': 'run'}]
        for mode, hint in (('human', '저장해야 확인할 수 있습니다'), ('tool', '저장해야 실행할 수 있습니다')):
            self.browser.call('Emulation.setDeviceMetricsOverride', {'width': 1366, 'height': 768, 'deviceScaleFactor': 1, 'mobile': False})
            key = self.author(name='입력 제안 보존 ' + mode, fields=fields, mode=mode,
                block='human_confirm' if mode == 'human' else 'values', jobs=2)
            run = self.start(key, inputs={'note': '서버에 저장된 값'}); self.open_run(key, run)
            before = deepcopy(self.state(run_id=run['id'])['run'])
            for width in (1366, 480):
                self.browser.call('Emulation.setDeviceMetricsOverride', {'width': width, 'height': 768, 'deviceScaleFactor': 1, 'mobile': False})
                self.wait('innerWidth === ' + str(width))
                writes = len(self.server.workspace_commands)
                self.preview_inputs(run, {'note': '도우미가 제안한 값'})
                self.input_tabs_roundtrip()
                self.assertTrue(self.browser.evaluate("!!document.querySelector('.ew-input-proposal-bar [data-action=apply_input_proposal]')"))
                self.assertEqual(self.read('[data-work-input][name=note]', 'value'), '서버에 저장된 값')
                self.click('[data-action=apply_input_proposal]')
                self.wait("document.querySelector('[data-work-input][name=note]')?.value === '도우미가 제안한 값'")
                self.input_tabs_roundtrip()
                self.applied_inputs_evidence(hint, 1, 'e2-a4a-' + mode + '-' + str(width))
                self.click('.ew-input-applied-bar [data-action=discard_inputs]')
                self.wait("document.querySelector('[data-work-input][name=note]')?.value === '서버에 저장된 값'")
                self.assertFalse(self.browser.evaluate("!!document.querySelector('.ew-input-applied-bar,.ew-input-proposal-applied,.ew-input-proposal-source')"))
                self.assert_only_selection_remembered(writes)
                self.assertEqual(self.state(run_id=run['id'])['run'], before)
            if mode == 'human':
                writes = len(self.server.workspace_commands)
                self.preview_inputs(run, {'note': '서버에 저장된 값'})
                self.click('[data-action=apply_input_proposal]')
                self.wait("!document.querySelector('.ew-input-proposal-bar')")
                self.assertEqual(self.read('[data-work-input][name=note]', 'value'), '서버에 저장된 값')
                self.assertFalse(self.browser.evaluate("!!document.querySelector('.ew-input-applied-bar,.ew-input-proposal-applied,.ew-input-proposal-source')"))
                self.preview_inputs(run, {'note': '먼저 반영한 제안 A'})
                self.click('[data-action=apply_input_proposal]')
                self.wait("document.querySelector('[data-work-input][name=note]')?.value === '먼저 반영한 제안 A'")
                self.preview_inputs(run, {'note': '나중에 받은 제안 B'})
                self.assertEqual(self.read('[data-work-input][name=note]', 'value'), '먼저 반영한 제안 A')
                self.assertEqual(self.text('.ew-input-proposal-source'), '도우미')
                self.click('[data-action=discard_input_proposal]')
                self.wait("!document.querySelector('.ew-input-proposal-bar')")
                self.assertEqual(self.read('[data-work-input][name=note]', 'value'), '먼저 반영한 제안 A')
                self.assertEqual(self.text('.ew-input-proposal-source'), '도우미')
                self.assertEqual(self.text('.ew-input-proposal-applied'), '저장 전')
                self.assertEqual(self.text('.ew-input-applied-bar > p'), hint)
                self.assertEqual(self.text('.ew-input-applied-bar [data-action=save_inputs]'), '입력 저장')
                self.click('.ew-input-applied-bar [data-action=discard_inputs]')
                self.wait("document.querySelector('[data-work-input][name=note]')?.value === '서버에 저장된 값'")
                self.assertFalse(self.browser.evaluate("!!document.querySelector('.ew-input-applied-bar,.ew-input-proposal-applied,.ew-input-proposal-source')"))
                self.assert_only_selection_remembered(writes)
                self.assertEqual(self.state(run_id=run['id'])['run'], before)
            # Scope changes clear both pending proposals and applied provenance.
            for applied in (False, True):
                self.preview_inputs(run, {'note': '다른 작업으로 가기 전 제안'})
                if applied:
                    self.click('[data-action=apply_input_proposal]')
                self.click('[data-action=overview]'); self.click('[data-action=job][data-job-id=job-1]')
                self.assertFalse(self.browser.evaluate("!!document.querySelector('.ew-input-proposal-bar,.ew-input-proposal-applied,.ew-input-proposal-source')"))
                self.click('[data-action=overview]'); self.click('[data-action=job][data-job-id=job-0]')
                self.assertFalse(self.browser.evaluate("!!document.querySelector('.ew-input-proposal-bar,.ew-input-proposal-applied,.ew-input-proposal-source')"))
            self.assertEqual(self.state(run_id=run['id'])['run'], before)

            self.preview_inputs(run, {'note': '명시적으로 저장할 제안'})
            self.click('[data-action=apply_input_proposal]')
            self.wait("document.querySelector('.ew-input-applied-bar [data-action=save_inputs]')")
            writes = len(self.server.workspace_commands)
            self.click('.ew-input-applied-bar [data-action=save_inputs]')
            self.wait("document.querySelector('#ees-work-inputs[data-settings=false]')?.dataset.revision === " + json.dumps(str(before['revision'] + 1)))
            saved = deepcopy(self.state(run_id=run['id'])['run'])
            self.assertEqual(saved['inputs']['note'], '명시적으로 저장할 제안')
            self.assertFalse(self.browser.evaluate("!!document.querySelector('.ew-input-applied-bar,.ew-input-proposal-applied,.ew-input-proposal-source')"))
            commands = self.server.workspace_commands[writes:]
            business = [body for body in commands if body.get('action') != 'save_ui']
            self.assertEqual([body.get('action') for body in business], ['save_inputs'], commands)
            self.assertEqual(business[0]['inputs'], {'note': '명시적으로 저장할 제안'})
            self.assertEqual(business[0]['expected_revision'], before['revision'])
            writes = len(self.server.workspace_commands)
            self.fill('[data-work-input][name=note]', '저장 뒤 직접 작성한 개인 초안')
            self.input_tabs_roundtrip()
            self.assertEqual(self.read('[data-work-input][name=note]', 'value'), '저장 뒤 직접 작성한 개인 초안')
            self.assertFalse(self.browser.evaluate("!!document.querySelector('.ew-input-applied-bar,.ew-input-proposal-applied,.ew-input-proposal-source')"))
            self.assertEqual(self.text('#ees-work-inputs [data-action=save_inputs]'), '입력 저장')
            self.assert_only_selection_remembered(writes)
            self.assertEqual(self.state(run_id=run['id'])['run'], saved)

    def test_e2_settings_tab_proposal_uses_run_draft_and_allows_separate_settings_save(self):
        key = self.author(name='업무 설정과 진행 건 제안 분리', jobs=1, fields=[
            {'id': 'note', 'name': '이번 메모', 'type': 'text', 'scope': 'run'},
            {'id': 'kept', 'name': '보존할 메모', 'type': 'text', 'scope': 'run'},
            {'id': 'setting', 'name': '공통 설정', 'type': 'text', 'scope': 'workflow'}])
        self.command('save_settings', workflow_id=key, values={'setting': '저장된 업무 설정'})
        run = self.start(key, inputs={'note': '저장된 진행 건 입력', 'kept': '저장된 보존 값'})
        self.open_run(key, run)
        before = deepcopy(self.state(run_id=run['id'])['run'])
        self.fill('[data-work-input][name=note]', '직접 작성한 진행 건 초안')
        self.fill('[data-work-input][name=kept]', '제안이 바꾸지 않을 개인 초안')
        self.click('[data-action=tab][data-tab=settings]')
        self.wait("document.querySelector('[data-work-input][name=setting]')?.value === '저장된 업무 설정'")

        def propose_on_settings(value):
            reference = self.browser.evaluate('window.__eesNativeWorkV1.captureReference()')
            payload = {'proposal_kind': 'inputs', 'workflow_id': key, 'run_id': run['id'], 'job_id': 'job-0',
                'base_revision': run['revision'], 'context_id': reference['context_id'], 'proposal': {'note': value}}
            result = self.browser.evaluate("window.__eesNativeWorkV1.propose('existing-chat'," + json.dumps(payload, ensure_ascii=False) + ")")
            self.assertTrue(result['ok'], result)
            self.assertFalse(result['saved'], result)
            self.assertEqual(self.read('[data-work-input][name=setting]', 'value'), '저장된 업무 설정')

        writes = len(self.server.workspace_commands)
        propose_on_settings('업무 설정에서 받은 진행 건 제안')
        self.click('[data-action=tab][data-tab=current]')
        self.wait("document.querySelector('.ew-input-proposal-bar [data-action=apply_input_proposal]')")
        self.assertEqual(self.read('[data-work-input][name=note]', 'value'), '직접 작성한 진행 건 초안')
        self.click('[data-action=apply_input_proposal]')
        self.wait("document.querySelector('[data-work-input][name=note]')?.value === '업무 설정에서 받은 진행 건 제안'")
        self.assertEqual(self.read('[data-work-input][name=kept]', 'value'), '제안이 바꾸지 않을 개인 초안')
        self.assertEqual(self.text('.ew-input-proposal-applied'), '저장 전')
        self.assertEqual(self.state(run_id=run['id'])['run'], before)
        self.assert_only_selection_remembered(writes)
        self.click('.ew-input-applied-bar [data-action=discard_inputs]')
        self.wait("document.querySelector('[data-work-input][name=note]')?.value === '저장된 진행 건 입력'")

        writes = len(self.server.workspace_commands)
        self.preview_inputs(run, {'note': '첫 번째 입력 제안', 'kept': '두 번째 입력 제안'})
        self.click('[data-action=apply_input_proposal]')
        self.wait("document.querySelectorAll('.ew-input-proposal-source').length === 2")
        self.click('[data-work-input][name=note]'); self.key('a', 65, 2)
        edited = '첫 값을 직접 고침'
        self.browser.call('Input.insertText', {'text': edited})
        self.assertFalse(self.browser.evaluate("!!document.querySelector('[data-work-input][name=note]').closest('.ew-input-row').querySelector('.ew-input-proposal-source')"))
        self.assertTrue(self.browser.evaluate("!!document.querySelector('[data-work-input][name=kept]').closest('.ew-input-row').querySelector('.ew-input-proposal-source')"))
        self.assertEqual(self.read('[data-work-input][name=kept]', 'value'), '두 번째 입력 제안')
        self.assertEqual(self.browser.evaluate("({name:document.activeElement.name,value:document.activeElement.value,start:document.activeElement.selectionStart,end:document.activeElement.selectionEnd})"),
            {'name': 'note', 'value': edited, 'start': len(edited), 'end': len(edited)})
        self.assertEqual(self.text('.ew-input-proposal-applied'), '저장 전')
        self.assertEqual(self.text('.ew-input-applied-bar > p'), '저장해야 확인할 수 있습니다')
        self.fill('[data-work-input][name=note]', '첫 번째 입력 제안')
        self.assertFalse(self.browser.evaluate("!!document.querySelector('[data-work-input][name=note]').closest('.ew-input-row').querySelector('.ew-input-proposal-source')"))
        self.assertEqual(self.read('[data-work-input][name=note]', 'value'), '첫 번째 입력 제안')
        self.assertTrue(self.browser.evaluate("!!document.querySelector('[data-work-input][name=kept]').closest('.ew-input-row').querySelector('.ew-input-proposal-source')"))
        self.assert_only_selection_remembered(writes)
        self.assertEqual(self.state(run_id=run['id'])['run'], before)
        self.click('.ew-input-applied-bar [data-action=discard_inputs]')
        self.wait("document.querySelector('[data-work-input][name=note]')?.value === '저장된 진행 건 입력'")

        self.preview_inputs(run, {'note': '첫 번째 입력 제안', 'kept': '두 번째 입력 제안'})
        self.click('[data-action=apply_input_proposal]')
        self.wait("document.querySelectorAll('.ew-input-proposal-source').length === 2")
        self.fill('[data-work-input][name=note]', '저장된 진행 건 입력')
        self.fill('[data-work-input][name=kept]', '저장된 보존 값')
        self.assertFalse(self.browser.evaluate("!!document.querySelector('.ew-input-proposal-source,.ew-input-proposal-applied,.ew-input-applied-bar')"))
        self.fill('[data-work-input][name=note]', '모든 제안을 지운 뒤 직접 작성')
        self.assertEqual(self.read('[data-work-input][name=note]', 'value'), '모든 제안을 지운 뒤 직접 작성')
        self.assertEqual(self.read('[data-work-input][name=kept]', 'value'), '저장된 보존 값')
        self.assertFalse(self.browser.evaluate("!!document.querySelector('.ew-input-proposal-source,.ew-input-proposal-applied,.ew-input-applied-bar')"))
        self.assert_only_selection_remembered(writes)
        self.assertEqual(self.state(run_id=run['id'])['run'], before)
        self.fill('[data-work-input][name=note]', '저장된 진행 건 입력')

        self.click('[data-action=tab][data-tab=settings]')
        self.wait("document.querySelector('[data-work-input][name=setting]')?.value === '저장된 업무 설정'")
        writes = len(self.server.workspace_commands)
        propose_on_settings('아직 반영하지 않은 다음 제안')
        self.fill('[data-work-input][name=setting]', '별도로 저장한 업무 설정')
        self.assertEqual(self.text('[data-action=save_inputs]'), '설정 저장')
        self.click('[data-action=save_inputs]')
        self.wait("document.querySelector('#ees-work-inputs[data-settings=true]')?.dataset.revision === '2'")
        saved = self.state(workflow_id=key, run_id=run['id'])
        # workspace_state returns raw scope rows under workflow.settings;
        # the launcher's top-level settings object is a client normalization.
        setting = next(item for item in saved['workflow']['settings'] if item['factory_id'] == '')
        self.assertEqual(setting['values']['setting'], '별도로 저장한 업무 설정')
        self.assertEqual(setting['revision'], 2)
        self.assertEqual(saved['run']['inputs'], before['inputs'])
        self.assertEqual(saved['run']['attempts'], before['attempts'])
        # The real server invalidates the effective work snapshot when a shared
        # input changes. Do not bypass that revision's existing stale protection.
        self.assertEqual(saved['run']['revision'], before['revision'] + 1)
        commands = self.server.workspace_commands[writes:]
        business = [body for body in commands if body.get('action') != 'save_ui']
        self.assertEqual([body.get('action') for body in business], ['save_settings'], commands)
        self.assertEqual(business[0]['values'], {'setting': '별도로 저장한 업무 설정'})
        self.assertEqual(business[0]['expected_revision'], 1)
        self.assertNotIn('inputs', business[0])
        self.assertFalse(self.browser.evaluate("!!document.querySelector('#ees-work-panel .ew-error[role=alert]')"))

    def test_e2_pending_input_proposal_reports_blocked_result_confirmation_without_call(self):
        self.shared_fixture()
        self.bridge.result = {'status': 'succeeded', 'completeness': 'complete',
            'items': [{'id': 'DOC-1', 'title': '합성 운영 문서', 'url': 'https://example.invalid/doc-1'}]}
        key = self.shared_workflow(jobs=1)
        run = self.execute(self.start(key, inputs={'query': '원래 찾을 말'})); self.open_run(key, run)
        self.wait("document.querySelector('[data-action=confirm_list]')")
        self.preview_inputs(run, {'query': '새로 제안한 찾을 말'})
        before = deepcopy(self.state(run_id=run['id'])['run'])
        writes = len(self.server.workspace_commands); calls = len(self.bridge.calls)
        self.click('[data-action=confirm_list]')
        self.wait("document.querySelector('#ees-work-panel [role=alert]')?.textContent.includes('업무 도우미 입력 제안을 먼저 반영하거나 버려 주세요.')")
        self.assertFalse(self.browser.evaluate("!!document.querySelector('#ees-work-dialog')"))
        self.assert_only_selection_remembered(writes)
        self.assertEqual(len(self.bridge.calls), calls)
        self.assertEqual(self.state(run_id=run['id'])['run'], before)
        self.screenshot('e2-pending-proposal-blocked-confirmation')

    def execute(self, run, job='job-0'):
        result = asyncio.run(self.server.workflow.operations.command(self.server.user,
            {'action': 'execute_job', 'run_id': run['id'], 'job_id': job,
             'expected_revision': run['revision'], 'request_id': str(uuid4())}))
        self.assertTrue(result['ok'], result)
        return self.state(run_id=run['id'])['run']

    def shared_fixture(self):
        """Synthetic installed metadata/transport; real approvals, registry and runs."""
        native = importlib.import_module(self.backend.__package__ + '.ees_workflow_native')
        source = (Path(__file__).resolve().parents[1] / 'agent-pack/skills/confluence-read/scripts/confluence_tool.py').read_text(encoding='utf-8')
        self.shared_reference = {'tool_id': 'synthetic-installed-confluence', 'revision': 0,
            'content_hash': native.MANAGED_READ_SOURCE_HASHES['confluence'], 'schema_hash': 'b' * 64,
            'config_hash': 'c' * 64, 'environment': 'd' * 64}
        self.shared_member = True
        self.shared_group = {'id': 'shared-readers', 'name': '조회 팀'}
        self.server.workflow.group_lookup = lambda _: [self.shared_group] if self.shared_member else []
        self.server.workflow.group_list_lookup = lambda: [self.shared_group]
        schemas = {
            'search_pages': {'type': 'object', 'properties': {'query': {'type': 'string'},
                'space_key': {'type': 'string', 'default': ''}, 'limit': {'type': 'integer', 'default': 5}}, 'required': ['query']},
            'get_page': {'type': 'object', 'properties': {'page_id': {'type': 'string'}}, 'required': ['page_id']}}

        async def managed():
            return [{'id': self.shared_reference['tool_id'], 'content': source}]

        async def inspect(actor, tool_id, function):
            reference = {**self.shared_reference, 'function': function}
            with self.server.workflow._db() as db:
                approval = db.execute('SELECT reference,state,revision FROM native_approvals WHERE tool_id=? AND function=?', (tool_id, function)).fetchone()
            reference['revision'] = approval['revision'] if approval else 0
            allowed = bool(approval and approval['state'] == 'allowed' and json.loads(approval['reference']) == reference)
            return {'reference': reference, 'schema': deepcopy(schemas[function]), 'state': 'allowed' if allowed else 'approval_required'}

        self.bridge.managed_tools, self.bridge.inspect = managed, inspect
        self.bridge.store_approval = lambda db, actor, reference, evidence: native.NativeBridge.store_approval(self.bridge, db, actor, reference, evidence)
        self.review_shared()

    def review_shared(self):
        registry = self.server.workflow.shared_tools
        item = next(item for item in asyncio.run(registry.list(self.server.user)) if item['id'] == 'managed-search_pages')
        result = asyncio.run(registry.command(self.server.user, {
            'action': 'shared_tool_review', 'expected_revision': item['revision'], 'request_id': str(uuid4()),
            'shared_tool_id': item['id'], 'reference': item['observed_reference'],
            'group_ids': ['shared-readers'], 'responsible_user_id': self.server.user['id'],
            'evidence': '합성 설치 원본의 입력과 결과 및 연결 설정을 확인했습니다.'}))
        self.assertTrue(result['ok'], result)

    def shared_workflow(self, *, jobs=2, shared=True):
        key = self.author(name='공용 찾기 실행 명세 검증' if shared else '이전 방식 부분 결과 검증', jobs=jobs)
        workflow = self.state(workflow_id=key)['workflow']
        definition = deepcopy(workflow['draft'])
        job = definition['nodes']['job-0']
        job.update(mode='tool', result_block='list_confirm', human_confirmation=True,
            assignee={'kind': 'user', 'id': self.server.user['id']},
            inputs=[{'id': 'query', 'name': '찾을 말', 'type': 'text', 'scope': 'run', 'required': True}],
            argument_bindings={'query': {'input': 'query'}})
        if shared:
            job['shared_tool_id'] = 'managed-search_pages'
        else:
            job['tool_reference'] = {'tool_id': 'synthetic-read', 'function': 'jira_dashboard', 'revision': 1,
                'content_hash': 'a' * 64, 'schema_hash': 'b' * 64}
        if jobs > 1:
            definition['nodes']['job-1']['deps'] = ['job-0']
        revision = workflow['revision']
        self.command('save_draft', workflow_id=key, expected_revision=revision, definition=definition)
        checked = self.command('validate_workflow', workflow_id=key, expected_revision=revision + 1)
        self.assertEqual(checked['validation']['errors'], [], checked)
        self.command('publish_workflow', workflow_id=key, expected_revision=revision + 1)
        return key

    def test_shared_runtime_normal_partial_confirmation_next_job_and_close_evidence(self):
        self.shared_fixture()
        # One flow proves the same explicit-human boundary for both read paths.
        for shared in (True, False):
            with self.subTest(shared=shared):
                self.bridge.result = {'status': 'succeeded', 'completeness': 'partial', 'scope': 'single_page',
                    'items': [{'id': 'DOC-1', 'title': '합성 운영 안내', 'url': 'https://example.invalid/doc-1'}]}
                key = self.shared_workflow(shared=shared)
                run = self.start(key, inputs={'query': '운영 안내'}); self.open_run(key, run)
                if shared:
                    self.assertIn('Confluence 페이지 찾기 · 회차 v1', self.text('.ew-shared-runtime'))
                    self.assertIn('개인 PAT(기존 방식)', self.text('.ew-shared-runtime'))
                    self.assertFalse(self.read('[data-action=execute]', 'disabled'))
                    self.screenshot('shared-runtime-normal')
                self.click('[data-action=execute]')
                self.wait("document.querySelector('.ew-list-confirm')?.innerText.includes('DOC-1')")
                before = self.state(run_id=run['id'])['run']
                self.assertEqual(before['jobs']['job-0']['status'], 'partial')
                self.assertFalse(before['jobs']['job-0'].get('partial_confirmed'))
                if shared:
                    self.assertIn('찾은 문서 앞쪽 1건', self.text('#ees-work-panel'))
                    self.assertIn('더 있을 수 있습니다. 필요한 문서를 골라 확정하면 다음 작업으로 넘어갑니다.', self.text('#ees-work-panel'))
                    self.screenshot('shared-runtime-partial-before-confirm')
                denied = asyncio.run(self.server.workflow.workspace_command(self.server.user, {
                    'action': 'human_confirm', 'run_id': run['id'], 'job_id': 'job-1',
                    'expected_revision': before['revision'], 'request_id': str(uuid4())}))
                self.assertFalse(denied['ok'], denied)
                self.assertEqual(self.state(run_id=run['id'])['run']['revision'], before['revision'])
                self.click('[data-action=confirm_list]')
                self.fill('#ees-list-confirm-reason', '받은 범위의 문서를 직접 확인했습니다.')
                self.click('[data-dialog-confirm]')
                self.wait("document.querySelector('.ew-list-confirm')?.innerText.includes('사람 확정 기록 있음')")
                confirmed = self.state(run_id=run['id'])['run']
                self.assertEqual(confirmed['jobs']['job-0']['status'], 'partial')
                self.assertTrue(confirmed['jobs']['job-0']['partial_confirmed'])
                self.click('[data-action=overview]'); self.click('[data-action=job][data-job-id=job-1]')
                self.assertIn('부분 결과에서 시작함', self.text('#ees-work-panel'))
                self.click('[data-action=confirm]'); self.click('[data-dialog-confirm]')
                self.wait("document.querySelector('#ees-work-panel .ew-work-heading .ew-status')?.dataset.status === 'completed'")
                self.click('[data-action=tab][data-tab=history]')
                self.click('.ew-history summary')
                self.assertIn('부분 결과에서 시작함', self.text('.ew-history'))
                if shared:
                    self.screenshot('shared-runtime-partial-next-history')
                self.click('[data-action=overview]'); self.click('[data-action=close_run]')
                self.click('[data-dialog-confirm]')
                self.wait("document.querySelector('#ees-work-panel')?.innerText.includes('읽기 전용')")
                closed = self.state(run_id=run['id'])['run']
                self.assertEqual(closed['status'], 'completed')
                self.assertEqual([item['job_id'] for item in closed['closure_summary']['partial_jobs']], ['job-0'])
                self.assertIn('부분 결과', self.text('#ees-work-panel'))
                if shared:
                    self.screenshot('shared-runtime-partial-closed')

    def test_shared_search_zero_rows_and_zero_selection_each_complete_once(self):
        self.shared_fixture()
        for empty in (True, False):
            with self.subTest(empty=empty):
                self.bridge.result = {'status': 'succeeded', 'completeness': 'empty' if empty else 'partial',
                    'scope': 'single_page', 'items': [] if empty else [
                        {'id': 'DOC-1', 'title': '조건과 다른 합성 문서', 'url': 'https://example.invalid/doc-1'}]}
                key = self.shared_workflow(jobs=1)
                run = self.execute(self.start(key, inputs={'query': '운영 안내'})); self.open_run(key, run)
                if empty:
                    self.assertIn('결과 없음', self.text('#ees-work-panel'))
                    self.assertIn('찾은 문서가 없습니다.', self.text('#ees-work-panel'))
                    self.assertNotIn('완결성 · 한 쪽', self.text('#ees-work-panel'))
                    self.assertNotIn('이번 검색에서 받은 페이지 목록입니다.', self.text('#ees-work-panel'))
                    self.assertEqual(self.text('[data-action=confirm_list]'), '찾은 문서 없음 확인')
                    self.screenshot('shared-runtime-zero-rows')
                else:
                    self.click('[data-list-include][data-item-id=DOC-1]')
                self.assertFalse(self.read('[data-action=confirm_list]', 'disabled'))
                original = deepcopy(self.state(run_id=run['id'])['run']['attempts'][0]['result'])
                self.click('[data-action=confirm_list]')
                if not empty:
                    self.assertIn('맞는 문서가 없는 것으로 확정할까요?', self.text('#ees-work-dialog'))
                    self.assertEqual(self.browser.evaluate('document.querySelectorAll("#ees-work-dialog [data-dialog-confirm]").length'), 1)
                    self.assertFalse(self.browser.evaluate('!!document.querySelector("#ees-list-confirm-reason")'))
                    self.screenshot('shared-runtime-zero-selection-question')
                    self.click('[data-dialog-confirm]')
                self.wait("document.querySelector('#ees-work-panel .ew-work-heading .ew-status')?.dataset.status === 'completed'")
                # Acceptance is immediate; the C3 exit may finish after the
                # service has already returned its completed business state.
                self.wait('!document.querySelector("#ees-work-dialog")')
                saved = self.state(run_id=run['id'])['run']
                self.assertEqual(saved['jobs']['job-0']['status'], 'completed')
                self.assertEqual(saved['attempts'][0]['result'], original)
                note = '0건 확인' if empty else '맞는 문서 없음 · 0개 선택'
                self.assertIn(note, json.dumps(saved['jobs']['job-0'], ensure_ascii=False))
                sent = [body for body in self.server.workspace_commands if body.get('action') == 'confirm_list' and body.get('run_id') == run['id']]
                self.assertEqual(len(sent), 1)
                self.screenshot('shared-runtime-zero-confirmed' if empty else 'shared-runtime-zero-selection-confirmed')

    def test_shared_runtime_group_review_version_and_running_gates(self):
        self.shared_fixture()
        key = self.shared_workflow(jobs=1)
        run = self.start(key, inputs={'query': '운영 안내'}); self.open_run(key, run)
        self.shared_member = False
        self.refresh()
        self.wait("document.querySelector('.ew-shared-runtime')?.innerText.includes('보기 전용')")
        self.assertIn('이 도구로 실행할 수 있는 사람 · 조회 팀', self.text('#ees-work-panel'))
        self.assertIn('지금 담당 · ' + self.server.user['name'], self.text('#ees-work-panel'))
        self.assertFalse(self.browser.evaluate('!!document.querySelector("[data-action=execute]")'))
        self.assertTrue(self.read('[data-work-input][name=query]', 'disabled'))
        self.screenshot('shared-runtime-outside-group')
        self.shared_member = True
        self.shared_reference['config_hash'] = 'e' * 64
        self.refresh()
        self.wait("document.querySelector('.ew-shared-runtime')?.innerText.includes('관리자에게 입력·결과와 연결 설정 확인을 요청하세요.')")
        self.assertTrue(self.read('[data-action=execute]', 'disabled'))
        self.assertFalse(self.browser.evaluate('!!document.querySelector("[data-action=shared_accept_version]")'))
        self.screenshot('shared-runtime-review-required')
        self.review_shared(); self.refresh()
        self.wait("document.querySelector('[data-action=shared_accept_version]')?.innerText === 'v2 버전으로 계속하기'")
        self.assertIn('회차 시작 뒤 도구가 v1에서 v2 버전으로 바뀌었습니다. 이 회차를 새 버전으로 계속할지 고르세요.', self.text('.ew-shared-runtime'))
        self.assertTrue(self.read('[data-action=execute]', 'disabled'))
        self.screenshot('shared-runtime-version-changed')
        # Queue the production coordinator without starting its worker. A queued
        # automatic round is not stopped, even though no J is running yet.
        current = self.state(run_id=run['id'])['run']
        queued = asyncio.run(self.server.workflow.operations.command(self.server.user, {
            'action': 'execute_scope', 'run_id': run['id'], 'node_id': 'stage',
            'expected_revision': current['revision'], 'request_id': str(uuid4())}))
        self.assertTrue(queued['ok'], queued)
        self.refresh()
        self.wait("!document.querySelector('[data-action=shared_accept_version]')")
        self.screenshot('shared-runtime-automatic-version-hidden')
        # The real worker stops on the version conflict; no read is dispatched.
        asyncio.run(self.server.workflow.operations.process_once())
        with self.server.workflow._db() as db:
            stopped = db.execute('SELECT status FROM work_scope_runs WHERE id=?', (queued['scope']['id'],)).fetchone()[0]
        self.assertEqual(stopped, 'blocked')
        self.assertEqual(self.bridge.calls, [])
        self.refresh()
        self.wait("document.querySelector('[data-action=shared_accept_version]')?.innerText === 'v2 버전으로 계속하기'")
        self.click('[data-action=shared_accept_version]'); self.click('[data-dialog-confirm]')
        self.wait("document.querySelector('.ew-shared-runtime')?.innerText.includes('회차 v2')")
        self.bridge.hold.clear(); self.bridge.started.clear()
        self.click('[data-action=execute]')
        self.assertTrue(self.bridge.started.wait(5))
        self.shared_reference['config_hash'] = 'f' * 64
        self.review_shared(); self.refresh()
        self.wait("document.querySelector('#ees-work-panel .ew-work-heading .ew-status')?.dataset.status === 'running'")
        self.assertFalse(self.browser.evaluate('!!document.querySelector("[data-action=shared_accept_version]")'))
        self.screenshot('shared-runtime-running-version-hidden')
        self.bridge.hold.set()
        self.wait("document.querySelector('#ees-work-panel .ew-work-heading .ew-status')?.dataset.status !== 'running'")

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
            {'id': 'wait', 'type': 'number', 'scope': 'run'},
            {'id': 'unbound', 'name': '요청에 연결하지 않은 값', 'type': 'text', 'scope': 'run'}])
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
        # Request rows follow the persisted tool schema's property order;
        # canonical JSON storage orders these keys as stop, target, wait.
        self.assertEqual(self.browser.evaluate("[...document.querySelectorAll('[data-work-input]')].map(field=>field.name)"), list(tool['input_schema']['properties']))
        before = deepcopy(self.state(run_id=run['id'])['run'])
        writes = len(self.server.workspace_commands)
        reference_context = self.browser.evaluate('window.__eesNativeWorkV1.captureReference()')
        payload = {'proposal_kind': 'inputs', 'workflow_id': key, 'run_id': run['id'], 'job_id': 'job-0',
            'base_revision': run['revision'], 'context_id': reference_context['context_id'],
            'proposal': {'target': '함께 거부할 대상', 'unbound': '보이지 않는 입력 제안'}}
        rejected = self.browser.evaluate("(() => {try{return window.__eesNativeWorkV1.propose('existing-chat'," + json.dumps(payload, ensure_ascii=False) + ");}catch(error){return {error:error.message};}})()")
        self.assertEqual(rejected, {'error': '현재 진행 건·작업·저장 버전과 다른 입력 제안입니다.'})
        self.assertEqual(self.read('[data-work-input][name=target]', 'value'), 'SYNTHETIC-AP')
        self.assertFalse(self.browser.evaluate("!!document.querySelector('[data-work-input][name=unbound],.ew-input-proposal-bar,.ew-input-applied-bar,.ew-input-proposal-applied,.ew-input-proposal-source')"))
        self.assert_only_selection_remembered(writes)
        self.assertEqual(self.state(run_id=run['id'])['run'], before)
        for width in (1366, 480):
            self.browser.call('Emulation.setDeviceMetricsOverride', {'width': width, 'height': 768, 'deviceScaleFactor': 1, 'mobile': False})
            self.wait('innerWidth === ' + str(width))
            writes = len(self.server.workspace_commands)
            self.preview_inputs(run, {'target': 'SYNTHETIC-AP-02', 'stop': 'force', 'wait': 30})
            self.click('[data-action=apply_input_proposal]')
            self.wait("document.querySelector('[data-work-input][name=target]')?.value === 'SYNTHETIC-AP-02'")
            self.input_tabs_roundtrip()
            self.applied_inputs_evidence('저장해야 요청할 수 있습니다', 3, 'e2-a4a-request-' + str(width))
            self.click('.ew-input-applied-bar [data-action=discard_inputs]')
            self.wait("document.querySelector('[data-work-input][name=target]')?.value === 'SYNTHETIC-AP'")
            self.assertEqual(json.loads(self.read('[data-work-input][name=stop]', 'value')), 'graceful')
            self.assertEqual(self.read('[data-work-input][name=wait]', 'value'), '60')
            self.assertFalse(self.browser.evaluate("!!document.querySelector('.ew-input-proposal-applied,.ew-input-proposal-source')"))
            self.assert_only_selection_remembered(writes)
            self.assertEqual(self.state(run_id=run['id'])['run']['inputs'], {'target': 'SYNTHETIC-AP', 'stop': 'graceful', 'wait': 60})
        self.browser.call('Emulation.setDeviceMetricsOverride', {'width': 1366, 'height': 768, 'deviceScaleFactor': 1, 'mobile': False})
        self.fill('#ees-request-reason', '합성 확인 사유')
        self.click('[data-action=request_intent]')
        self.wait("document.querySelector('#ees-work-dialog')?.innerText.includes('합성 확인 사유')")
        self.assertIn('SYNTHETIC-AP', self.text('#ees-work-dialog'))
        self.click('[data-dialog-confirm]')
        self.wait("document.querySelector('#ees-work-panel')?.innerText.includes('연결')")
        with self.server.workflow._db() as db:
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
        # The shared-search exception must not enable legacy zero-row completion.
        self.bridge.result = {'status': 'succeeded', 'completeness': 'complete', 'items': []}
        empty_key = self.author(mode='tool', block='list_confirm', jobs=1, name='합성 빈 목록')
        empty_run = self.execute(self.start(empty_key)); self.open_run(empty_key, empty_run)
        self.assertIn('조회 0건', self.text('.ew-list-confirm'))
        self.assertTrue(self.read('[data-action="confirm_list"]', 'disabled'))
        self.click('[data-action="save_list_selection"]')
        self.fill('#ees-list-confirm-reason', '이전 방식 조회 0건은 완료하지 않고 선택 상태만 저장')
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
