"""Opt-in, unpublished delivery-check definition used only by tests.

It is authored through production commands; nothing imports this as product seed.
Native references and the actual Jira project/date/status mapping are supplied by
current registry/metadata reads, never inferred from an EES system name.
"""
from copy import deepcopy


def definition_from_draft(draft, references):
    definition = deepcopy(draft)
    definition.update(name='합성 배포 산출물 점검', completion_policy='all_required_approved',
                      unapproved_policy='hold', delivery_policy='draft_only')
    root = next(iter(definition['nodes']))
    definition['nodes'][root]['children'] = ['stage-review']
    order = ['cr-list', 'documents', 'verdict', 'report']
    definition['nodes']['stage-review'] = {'id': 'stage-review', 'type': 't', 'name': '자료 확인과 기록',
        'parent': root, 'children': order, 'deps': []}
    def job(id, name, mode, block, deps):
        return {'id': id, 'type': 'j', 'parent': 'stage-review', 'children': [], 'deps': deps,
                'name': name, 'mode': mode, 'result_block': block, 'inputs': [], 'human_confirmation': True}
    def choice(id, name, path, multi=False):
        dependency = [] if path == 'projects' else ['project']
        return {'id': id, 'name': name, 'type': 'multi' if multi else 'single', 'scope': 'run', 'required': True,
            'options_source': 'tool', 'depends_on': dependency, 'options': [], 'options_query': {
                'reference': deepcopy(references['jira_project_metadata']),
                'argument_bindings': {'project_key': {'input': 'project'} if dependency else {'constant': ''}},
                'result_path': [path], 'value_field': 'id', 'label_field': 'name'}}
    query = job('cr-list', '실제 Jira 조건으로 CR 목록 조회·확정', 'tool', 'list_confirm', [])
    query['inputs'] = [choice('project', 'Jira 프로젝트', 'projects'), choice('statuses', '조회 상태', 'statuses', True),
        choice('date_field', '배포일 매핑', 'date_fields'),
        *[{'id': id, 'name': name, 'type': 'datetime', 'scope': 'run', 'required': True} for id, name in [('from_date', '시작 날짜'), ('to_date', '종료 날짜')]]]
    query['tool_reference'] = deepcopy(references['jira_search_crs'])
    query['argument_bindings'] = {arg: {'input': field} for arg, field in {'project_key': 'project', 'status_ids': 'statuses', 'date_field': 'date_field', 'start_date': 'from_date', 'end_date': 'to_date'}.items()}
    docs = job('documents', '확정 CR 전체의 첨부 존재·접근 확인', 'tool', 'checklist', ['cr-list'])
    docs['inputs'] = [{'id':'required_filenames','name':'필수 문서의 정확한 파일 이름','type':'list','scope':'run','required':True}]
    docs['tool_reference'] = deepcopy(references['jira_cr_attachments'])
    docs['argument_bindings'] = {'issue_keys': {'result': {'job_id': 'cr-list', 'path': ['items'], 'value_field': 'id', 'confirmed': True}}, 'required_filenames': {'input':'required_filenames'}}
    docs['instructions'] = '첨부 이름·존재·접근 결과를 확인한다. 내용 적정성을 승인한 결과가 아니다.'
    verdict = job('verdict', '근거 기반 AI 제안과 CR별 사람 판정', 'ai', 'item_verdict', ['cr-list', 'documents'])
    verdict['result_source_job_id'] = 'cr-list'
    verdict['instructions'] = '첨부 이름·접근 상태를 근거로 제안한다. 내용 미검토는 판단 불가이며 사람 판정을 대신하지 않는다.'
    report = job('report', '결과 초안 저장·검토', 'ai', 'ai_review', ['verdict'])
    report['dependency_policy'] = 'all_resolved'
    report['instructions'] = '사람 판정과 근거를 정확히 보존한 결과 초안을 작성한다. 미승인 CR의 포함·제외와 송부를 실행하지 않는다.'
    for node in (query, docs, verdict, report): definition['nodes'][node['id']] = node
    return definition
