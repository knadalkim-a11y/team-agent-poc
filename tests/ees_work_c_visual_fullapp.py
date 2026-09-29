"""C-view visual evidence on the official CLI app, never a fixture frontend.

The temporary procedure mirrors the reference workload counts and state volume;
retained legacy check labels are recorded as content differences. Setup uses
supported authoring/workflow APIs; chat content is
created by the real composer. No DOM style, layout, timer, or screenshot mask is
applied. 1920x1080 originals and 1920x1048 effective-app captures are distinct.
"""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import time
from uuid import uuid4
from zipfile import ZipFile


QUESTION = '연결 확인이랑 응답 확인은 뭐가 달라?'
ANSWER = ('연결 확인은 대상에 접근할 수 있는지, 응답 확인은 요청을 정상 처리하는지 보는 점검이에요.\n\n'
          '두 항목이 모두 통과해야 이 작업이 완료됩니다.\n'
          '현재 화면은 모의 점검 예시여서 실제 DB에 접속하지 않습니다.')


def audit_visual_source(source_root, upstream_wheel, wheel, out):
    """Compare packaged EES assets to the explicitly named immutable source.

    Builder/Native patch-source hashes are recorded for the separate full-wheel
    audit; the asset check is not represented as a full repack comparison.
    """
    source_root, upstream_wheel, wheel, out = map(lambda path: Path(path).resolve(),
                                                (source_root, upstream_wheel, wheel, out))
    builder_path = source_root/'scripts/build_ees_webui.py'
    spec = importlib.util.spec_from_file_location('ees_visual_source_builder', builder_path)
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    upstream_hash = hashlib.sha256(upstream_wheel.read_bytes()).hexdigest()
    assert upstream_hash == builder.SOURCE_SHA256
    with ZipFile(upstream_wheel) as original, ZipFile(wheel) as product:
        expected = builder.prepare_additions(original, builder.UI_DIR)
        mismatches = [name for name, value in expected.items()
                      if name not in product.namelist() or product.read(name) != value]
    result = {'source_root': str(source_root), 'source_commit': subprocess.check_output(
                  ['git', '-C', str(source_root), 'rev-parse', 'HEAD'], text=True, encoding='utf-8').strip(),
              'source_dirty': bool(subprocess.check_output(['git', '-C', str(source_root), 'status', '--porcelain'],
                                   text=True, encoding='utf-8').strip()),
              'wheel': str(wheel), 'wheel_sha256': hashlib.sha256(wheel.read_bytes()).hexdigest(),
              'upstream_sha256': upstream_hash, 'matched_assets': len(expected) - len(mismatches),
              'asset_paths': list(expected),
              'mismatches': mismatches, 'builder_sha256': hashlib.sha256(builder_path.read_bytes()).hexdigest(),
              'boundary': 'Packaged EES additions compared byte-for-byte; Native patched chunks/full wheel audited separately'}
    (out/'source-audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    assert not mismatches, result
    return result


def authoring_only_gate(*, out, client, headers, browser, base, chat_id, click, wait, shot, record):
    """Minimal actual entry regression, with the original published procedure."""
    from ees_work_c_visual_interactions import authoring_gate
    response = client.post('/api/ees-work/action', headers=headers, json={
        'action': 'create', 'chat_id': chat_id,
        'payload': {'site_id': 'kr-ca', 'system': 'EMS', 'process_id': 'setup-p'}})
    response.raise_for_status()
    state = response.json()
    assert state['ok'] and state['case']['system'] == 'EMS'
    response = client.post('/api/v1/users/user/settings/update', headers=headers, json={
        'ui': {'language': 'ko-KR', 'theme': 'light', 'showChangelog': False}})
    response.raise_for_status()
    browser.events.clear()
    browser.call('Page.navigate', {'url': base + '/c/' + chat_id})
    deadline = time.monotonic() + 20
    while not any(event.get('method') == 'Page.loadEventFired' for event in browser.events):
        browser.events.append(browser.receive(deadline))
    wait('!!document.querySelector("#chat-input.ProseMirror") && !!document.querySelector("#ees-work-context-open")')
    if not browser.evaluate('!!document.querySelector("#ees-work-panel")?.getClientRects().length'):
        click('#ees-work-context-open')
    wait('!!document.querySelector("#ees-work-authoring-link")')
    click('#ees-work-tree [data-action="select"][data-node-id="install-t"]')
    wait('document.querySelector("#ees-work-panel .ew-title")?.textContent === "시스템 설치"')
    result = authoring_gate(browser=browser, click=click, wait=wait, shot=shot)
    result['setup_boundary'] = 'Original published setup-p; temporary real EMS case; no procedure edits, no repeated visual or composer suite'
    (out/'authoring-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    record('Actual current process authoring and Native Workspace entry', **result)


def visual_gate(*, out, client, headers, browser, base, chat_id, provider, click, wait, shot, record,
                interactions=False, file_only=False, layout_check=False):
    def api(path, body=None, **params):
        response = client.request('POST' if body is not None else 'GET', path,
                                  headers=headers, json=body, params=params or None)
        assert response.status_code < 400, (path, response.status_code, response.text)
        result = response.json()
        assert not isinstance(result, dict) or result.get('ok') is not False, result
        return result

    def author(action, process, payload):
        return api('/api/ees-work/authoring/action', {
            'action': action, 'request_id': uuid4().hex, 'system_id': process['owner_system'],
            'process_id': process['process_id'], 'expected_draft_revision': process['draft_revision'],
            'expected_owner_revision': process['owner_revision'], 'payload': payload})

    process = api('/api/ees-work/authoring', system_id='UNASSIGNED', process_id='setup-p')['process']
    workflow = deepcopy(process['workflow'])
    nodes = workflow['nodes']
    nodes['setup-p']['skills'] = []
    nodes['prep-t']['name'] = '사전 준비'
    nodes['infra-t']['name'] = 'AP·DB 인프라 준비'
    nodes['interface-t']['name'] = '인터페이스 확인'
    nodes['install-t']['description'] = '설치 설정 검토, DB 연결 확인과 AP 서비스 점검을 관리합니다.'
    nodes['install-t']['rule'] = '적용 작업 48개 모두 완료'
    nodes['db-j'].update(description='등록된 DB 대상의 연결 가능 여부와 정상 응답 여부를 확인합니다.',
                         rule='연결·응답 확인 모두 통과', tools=['gateway', 'db-read'],
                         bindings={'gateway': 'db', 'db-read': 'db'}, deps=['install-j'])
    template = deepcopy(nodes['scope-j'])
    def manual(identifier, parent, name):
        return dict(deepcopy(template), id=identifier, parent=parent, name=name,
                    description='', deps=[], skills=[], tools=[], bindings={}, condition='all')
    nodes['new-service'] = dict(deepcopy(nodes['ap-j']), id='new-service', name='서비스 상태 확인',
                                 parent='install-t', deps=['install-j'])
    nodes['ap-j']['deps'] = ['db-j']
    nodes['new-review'] = manual('new-review', 'install-t', '인터페이스 설정 검토')
    nodes['new-review']['mode'] = 'draft'
    nodes['new-equipment'] = manual('new-equipment', 'install-t', '설비 매핑 확인')
    nodes['install-t']['children'] = ['db-j', 'new-service', 'ap-j', 'new-review', 'new-equipment', 'install-j']
    counts = {'prep-t': 18, 'infra-t': 24, 'install-t': 48, 'interface-t': 30}
    completed = {'prep-t': 18, 'infra-t': 21, 'install-t': 25, 'interface-t': 8}
    for task, total in counts.items():
        children = nodes[task]['children']
        while len(children) < total:
            identifier = 'new-' + task + '-' + str(len(children) + 1)
            nodes[identifier] = manual(identifier, task, nodes[task]['name'] + ' 확인 ' + str(len(children) + 1))
            children.append(identifier)
    empty_input_nodes = ['db-j', *nodes['install-t']['children'][-3:], *nodes['infra-t']['children'][-3:]]
    ready_nodes = nodes['install-t']['children'][30:32]
    for identifier in empty_input_nodes[1:]:
        nodes[identifier].update(mode='tool', tools=['gateway'], bindings={'gateway': 'db'})
    for identifier in ready_nodes:
        nodes[identifier].update(mode='tool', tools=['gateway'], bindings={'gateway': 'db'})
    response = author('save_draft', process, {'workflow': workflow})
    mapping = response.get('id_map', {})
    process = response['process']
    process = author('validate_draft', process, {})['process']
    process = author('publish', process, {})['process']
    definition = process['workflow']
    state = api('/api/ees-work/action', {'action': 'create', 'chat_id': chat_id,
                'payload': {'site_id': 'kr-ca', 'system': 'EMS', 'process_id': 'setup-p'}})
    def current():
        return api('/api/ees-work/state', chat_id=chat_id)
    def action(name, node='', payload=None):
        nonlocal state
        case = state['case']
        state = api('/api/ees-work/action', {'action': name, 'chat_id': chat_id, 'case_id': case['id'],
                    'expected_revision': case['revision'], 'node_id': node, 'payload': payload or {}})
        return state
    for task, done in completed.items():
        children = definition['nodes'][task]['children']
        targets = (['install-j'] + children[6:30]) if task == 'install-t' else (
            children[1:done+1] if task == 'interface-t' else children[:done])
        for identifier in targets:
            # Records are prepared only in the isolated synthetic store through
            # the existing declared manual/mock path, not live business tools.
            action('run', identifier, {'confirm': True})
    action('run', mapping.get('new-service', 'new-service'), {'confirm': True})
    for identifier in empty_input_nodes:
        action('update_inputs', mapping.get(identifier, identifier), {'inputs': {'db': ''}})
    for identifier in ready_nodes:
        action('update_inputs', mapping.get(identifier, identifier), {'inputs': {'db': '테스트 DB-A · 예시'}})
    action('select', 'db-j')
    assert state['case']['progress'] == {'done': 72, 'total': 120}, state['case']['progress']
    assert state['case']['node_states']['install-t']['progress'] == {'done': 25, 'total': 48}
    assert state['case']['node_states']['install-t']['attention_count'] == 5
    assert state['case']['node_states']['install-t']['ready_count'] == 2
    api('/api/v1/users/user/settings/update', {'ui': {'language': 'ko-KR', 'theme': 'light',
         'showChangelog': False, 'models': ['c3-synthetic-model']}})
    api('/api/v1/models/create', {'id': 'c3-synthetic-model', 'name': 'EES Assistant',
                                 'meta': {},
                                 'params': {}, 'access_grants': []})
    api('/api/v1/chats/' + chat_id, {'chat': {'title': '업무 대화'}})
    api('/api/models')
    provider.native_content = ANSWER
    browser.events.clear()
    browser.call('Page.navigate', {'url': base + '/c/' + chat_id})
    deadline = time.monotonic() + 20
    while not any(event.get('method') == 'Page.loadEventFired' for event in browser.events):
        browser.events.append(browser.receive(deadline))
    wait('!!document.querySelector("#chat-input.ProseMirror") && !!document.querySelector("#ees-work-context-open")')
    if browser.evaluate('document.querySelector("#sidebar").getBoundingClientRect().width < 200'):
        click('button[aria-label="사이드바 열기"],button[aria-label="Open sidebar"]')
    wait('document.querySelector("#sidebar").getBoundingClientRect().width > 200')
    if not browser.evaluate('!!document.querySelector("#ees-work-panel")?.getClientRects().length'):
        click('#ees-work-context-open')
    wait('document.querySelector("#ees-work-panel .ew-title")?.textContent === "DB 연결 확인"')
    click('#chat-input')
    browser.call('Input.insertText', {'text': QUESTION})
    wait('!!document.querySelector("#send-message-button") && !document.querySelector("#send-message-button").disabled')
    click('#send-message-button')
    wait('document.querySelector("#chat-container")?.innerText.includes("현재 화면은 모의 점검 예시여서 실제 DB에 접속하지 않습니다.")')
    assert len(provider.models) == 1
    evidence = {'boundary': 'Official Native CLI/auth/chat/EES/temp DB; synthetic workflow via supported API; loopback model answer only',
                'model_profile_fixture': 'Default official model avatar; no custom image masking',
                'reference_notice_height': 32, 'captures': [], 'synthetic_workload': {
                    'process_jobs': 120, 'process_completed': 72, 'task_jobs': 48, 'task_completed': 25,
                    'ready_declared_mock_jobs': 2,
                    'prepared_via': 'real temporary authoring and declared legacy manual/mock action APIs',
                    'existing_tools_reused': ['gateway', 'db-read'],
                    'reference_difference': 'Two legacy check names/purposes and the existing site line are retained; authoring cannot redefine mock tools or mutate the global site catalog'}}

    def capture(label, reference, sizes=None):
        wait('!document.querySelector("#ees-work-panel")?.matches("[aria-busy=true]")')
        point = browser.evaluate('(()=>{const r=document.querySelector("#ees-work-content").getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+Math.min(r.height/2,100)};})()')
        browser.call('Input.dispatchMouseEvent', dict(type='mouseWheel', deltaX=0, deltaY=-10000, **point))
        wait('document.querySelector("#ees-work-content").scrollTop === 0')
        browser.call('Input.dispatchMouseEvent', {'type': 'mouseMoved', 'x': 1050, 'y': 20})
        browser.evaluate('document.fonts.ready')
        for width, height, suffix in (sizes or ((1920, 1080, 'viewport-original'), (1920, 1048, 'app-aligned'))):
            browser.call('Emulation.setDeviceMetricsOverride', {'width': width, 'height': height,
                         'deviceScaleFactor': 1, 'mobile': False})
            browser.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
            name = 'visual-' + label + '-' + suffix
            geometry = browser.evaluate('''(()=>{
              const selectors={sidebar:'#sidebar',workEntry:'#ees-work-entry',chat:'.ees-work-chat-column',chatPane:'#chat-pane',
                chatContainer:'#chat-container',messages:'#messages-container',composer:'#chat-input',
                composerForm:'#message-input-container',work:'#ees-work-panel',header:'#ees-work-panel > header',
                title:'#ees-work-panel .ew-title',content:'#ees-work-content',footer:'#ees-work-action-dock',
                context:'#ees-work-context',input:'#ees-work-inputs, .ew-work-target',action:'.ew-work-action-region',
                brand:'[data-ees-native-sidebar] > div > .sidebar:first-child > a:first-child',
                brandIcon:'[data-ees-native-sidebar] > div > .sidebar:first-child > a:first-child',
                brandTitle:'#sidebar-webui-name',newChat:'#sidebar-new-chat-button',searchNav:'#sidebar-search-button',
                brandHeader:'[data-ees-native-sidebar] > div > .sidebar:first-child',
                chatNavigation:'[data-ees-native-navigation] > div:first-child',scope:'.ew-scope-pickers',
                contextTitle:'.ew-chat-title',contextPath:'.ew-chat-path',statusBadge:'#ees-work-identity-slot .ew-badge, #ees-work-content .ew-work-identity .ew-badge',
                targetControl:'#ees-work-inputs input, .ew-work-target-field',saveButton:'#ees-work-inputs-save',runButton:'#ees-work-run',
                progressSummary:'.ew-work-metrics',jobSearch:'.ew-work-search',jobSearchInput:'#ees-work-job-search',jobFilters:'.ew-work-filters',
                jobTable:'.ew-work-job-table',jobMethod:'.ew-work-job-table tbody tr:first-child td:nth-child(2)',
                jobMethodHeading:'.ew-work-job-table th:nth-child(2)',jobState:'.ew-work-job-table tbody tr:first-child td:nth-child(3)',
                jobConditionToggle:'.ew-work-job-table tbody tr:first-child .ew-work-condition-toggle',nativeToolbar:'[data-ees-native-toolbar]',
                userBubble:'.chat-user .justify-end > div.rounded-3xl.bg-gray-50',userParagraph:'.chat-user .markdown-prose > p',
                assistantAvatar:'.assistant-message-profile-image',assistantName:'#response-message-model-name',
                assistantLead:'.chat-assistant .markdown-prose > p:first-of-type',assistantDetail:'.chat-assistant .markdown-prose > p:nth-of-type(2)',
                criterion:'.ew-work-criterion',scopeAction:'.ew-work-scope-action',scopeRunButton:'.ew-work-scope-action .ew-work-actions button',
                scopeReady:'.ew-work-ready',scopeBoundary:'.ew-work-scope-boundary',progressRegion:'.ew-work-progress',
                pagination:'.ew-work-pagination',newChatIcon:'[data-ees-native-navigation] #sidebar-new-chat-button > div:first-child',
                newChatLabel:'[data-ees-native-navigation] #sidebar-new-chat-button > div:nth-child(2) > div',
                searchNavIcon:'[data-ees-native-navigation] #sidebar-search-button svg',searchNavLabel:'[data-ees-native-navigation] #sidebar-search-button > div'};
              const measure=e=>{if(!e)return null;const s=getComputedStyle(e),r=e.getBoundingClientRect();
                return {tag:e.tagName,id:e.id,className:typeof e.className==='string'?e.className:'',text:e.innerText?.slice(0,300),
                  rect:r.toJSON(),clientWidth:e.clientWidth,clientHeight:e.clientHeight,scrollWidth:e.scrollWidth,
                  scrollHeight:e.scrollHeight,scrollTop:e.scrollTop,display:s.display,position:s.position,
                  fontFamily:s.fontFamily,fontSize:s.fontSize,lineHeight:s.lineHeight,fontWeight:s.fontWeight,
                  padding:s.padding,margin:s.margin,gap:s.gap,color:s.color,background:s.backgroundColor,
                  border:s.border,borderRadius:s.borderRadius,overflowX:s.overflowX,overflowY:s.overflowY,
                  ariaLabel:e.getAttribute('aria-label'),title:e.getAttribute('title'),
                  visible:!!e.getClientRects().length};};
              const ancestors=e=>{const result=[];for(let depth=0;e&&depth<8;e=e.parentElement,depth++)result.push(measure(e));return result;};
              const targets=Object.fromEntries(Object.entries(selectors).map(([k,v])=>[k,measure([...document.querySelectorAll(v)].find(e=>e.getClientRects().length)||document.querySelector(v))]));
              const navNodes=['#sidebar-new-chat-button','#sidebar-search-button'].map(s=>document.querySelector(s)).filter(Boolean);
              if(navNodes.length===2){const rr=navNodes.map(e=>e.getBoundingClientRect()),x=Math.min(...rr.map(r=>r.left)),y=Math.min(...rr.map(r=>r.top)),right=Math.max(...rr.map(r=>r.right)),bottom=Math.max(...rr.map(r=>r.bottom));
                targets.chatNavigation={rect:{x,y,width:right-x,height:bottom-y,left:x,top:y,right,bottom},visible:true,
                  mapping_note:'Measured union of the two actual Native navigation controls; no shared row box exists. Container style fields intentionally unmeasured.',
                  elements:navNodes.map(measure)};}
              return {viewport:{width:innerWidth,height:innerHeight,dpr:devicePixelRatio},
                document:{scrollWidth:document.documentElement.scrollWidth,scrollHeight:document.documentElement.scrollHeight},
                targets,
                ancestors:Object.fromEntries(['#chat-container','#chat-pane','#ees-work-context','#chat-input','#chat-input-container','#message-input-container','[data-ees-native-toolbar]'].map(v=>[v,ancestors(document.querySelector(v))])),
                controls:[...document.querySelectorAll('#ees-work-panel button,#ees-work-panel input,#ees-work-entry button,#chat-container button')].filter(e=>e.getClientRects().length).map(measure),
                metricDetails:[...document.querySelectorAll('.ew-work-progress,.ew-work-metrics > [data-work-metric],.ew-work-metrics > [data-work-metric] > span,.ew-work-metrics > [data-work-metric] > strong,.ew-work-metrics strong > span,.ew-work-metrics strong small,.ew-work-attention-detail,.ew-work-job-table thead,.ew-work-job-table tr,.ew-work-pagination,.ew-work-scope-action')].map(measure),
                sections:[...document.querySelectorAll('#ees-work-panel h2,#ees-work-panel h3,#ees-work-panel .ew-section,#ees-work-panel .ew-work-result')].map(measure)};
            })()''')
            geometry.update(reference_node=reference, alignment={'kind': suffix,
                'reference_app_origin': {'x': 0, 'y': 32}, 'product_app_origin': {'x': 0, 'y': 0},
                'pixel_scale': 1, 'css_or_dom_overrides': False,
                'note': 'Separate actual viewport rendering; no image crop, scaling or mask'})
            (out/(name + '.json')).write_text(json.dumps(geometry, ensure_ascii=False, indent=2), encoding='utf-8')
            shot(name)
            evidence['captures'].append({'name': name, 'reference_node': reference, 'viewport': geometry['viewport']})
        browser.call('Emulation.setDeviceMetricsOverride', {'width': 1920, 'height': 1080,
                     'deviceScaleFactor': 1, 'mobile': False})

    try:
        click('#ees-work-inputs input[name="db"]')
        for kind in ('keyDown', 'keyUp'):
            browser.call('Input.dispatchKeyEvent', {'type': kind, 'key': 'a', 'code': 'KeyA',
                         'modifiers': 2, 'windowsVirtualKeyCode': 65})
        browser.call('Input.insertText', {'text': '테스트 DB-A · 예시'})
        click('#ees-work-panel .ew-title')
        capture('j-input-before', '582:132')
        if interactions or layout_check:
            click('.ew-workflow-summary [data-action="select"][data-node-id="setup-p"]')
            wait('document.querySelector("#ees-work-panel .ew-title")?.textContent === "신규 공장 횡전개"')
            capture('p-management', '586:555')
        click('#ees-work-tree [data-action="select"][data-node-id="install-t"]')
        wait('document.querySelector("#ees-work-panel .ew-title")?.textContent === "시스템 설치"')
        click('[data-action="job_condition"][data-node-id="ap-j"]')
        capture('t-management', '586:958')
        click('#ees-work-content [data-work-job="db-j"] [data-action="select"]')
        wait('document.querySelector("#ees-work-panel .ew-title")?.textContent === "DB 연결 확인"')
        click('#ees-work-inputs-save')
        wait('!document.querySelector("#ees-work-panel")?.matches("[aria-busy=true]")')
        if interactions or layout_check:
            capture('j-input-saved', '584:169')
        click('#ees-work-run')
        wait('document.querySelector("#ees-work-panel").innerText.includes("완료") && !document.querySelector("#ees-work-panel").matches("[aria-busy=true]")')
        assert current()['case']['jobs']['db-j']['status'] == 'passed'
        capture('j-complete', '584:1098')
        click('.ew-work-action-region [data-action="panel_parent"]')
        wait('document.querySelector("#ees-work-panel .ew-title")?.textContent === "시스템 설치"')
        capture('t-after-completion', '586:1397')
        if interactions or layout_check:
            click('#ees-work-content [data-work-job="' + mapping['new-service'] + '"] [data-action="select"]')
            wait('document.querySelector("#ees-work-panel .ew-title")?.textContent === "서비스 상태 확인"')
            capture('j-declared-simulation-failed', None)
            evidence['additional_state_boundary'] = {
                'failure': 'Actual first declared AP simulation failure on 서비스 상태 확인; not a fabricated DB failure or exact Figma DB state',
                'running': 'Not captured: legacy mock is synchronous; no artificial saved-state or timer injection'}
            click('#ees-work-tree [data-action="select"][data-node-id="install-t"]')
            wait('document.querySelector("#ees-work-panel .ew-title")?.textContent === "시스템 설치"')
        if interactions or file_only:
            from ees_work_c_visual_interactions import interaction_gate
            evidence['interactions'] = interaction_gate(out=out, browser=browser, click=click, wait=wait,
                shot=shot, capture=capture, api=api, current=current, provider=provider, base=base, chat_id=chat_id, only_file=file_only)
        if layout_check:
            from ees_work_c_visual_interactions import authoring_gate, layout_gate
            evidence['layout_check'] = layout_gate(browser=browser, click=click, wait=wait, shot=shot, capture=capture)
            evidence['authoring_entry'] = authoring_gate(browser=browser, click=click, wait=wait, shot=shot)
        evidence['ok'] = True
        record('Official Native C visual captures', count=len(evidence['captures']),
               native_composer_sends=1 + int(interactions) + int(interactions or file_only),
               synthetic_workload=evidence['synthetic_workload'], visual_match_verdict='not inferred from capture success')
    finally:
        (out/'visual-result.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
