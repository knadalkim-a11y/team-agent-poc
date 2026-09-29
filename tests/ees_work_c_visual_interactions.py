"""Focused changed-surface interactions on the same official Native app.

This is optional after the equal-content captures. It uses actual CDP keyboard,
pointer and file-chooser events, no replacement DOM, styles or service calls.
The external model answer and embedding vectors are loopback synthesis.
"""
import json
import time


def p_impact_gate(*, browser, click, wait, shot, capture, api):
    """One final P-only dark/small-screen check through ordinary preferences."""
    click('.ew-workflow-summary [data-action="select"][data-node-id="setup-p"]')
    wait('document.querySelector("#ees-work-panel .ew-title")?.textContent === "신규 공장 횡전개"')
    api('/api/v1/users/user/settings/update', {'ui': {'language': 'ko-KR', 'theme': 'dark',
        'showChangelog': False, 'models': ['c3-synthetic-model']}})
    browser.evaluate('localStorage.setItem("theme","dark")')
    browser.events.clear()
    browser.call('Page.reload')
    deadline = time.monotonic() + 15
    while not any(event.get('method') == 'Page.loadEventFired' for event in browser.events):
        browser.events.append(browser.receive(deadline))
    wait('!!document.querySelector("#chat-input.ProseMirror") && document.documentElement.classList.contains("dark")')
    if not browser.evaluate('!!document.querySelector("#ees-work-panel")?.getClientRects().length'):
        click('#ees-work-context-open')
    browser.call('Emulation.setDeviceMetricsOverride', {'width': 1366, 'height': 768,
                 'deviceScaleFactor': 1, 'mobile': False})
    wait('!!document.querySelector(".ew-work-stage-table") && !!document.querySelector(".ew-work-scope-action button")')
    click('#ees-work-panel .ew-title')
    found = False
    for _ in range(100):
        if browser.evaluate('document.activeElement?.matches(".ew-work-scope-action button")'):
            found = True
            break
        for kind in ('keyDown', 'keyUp'):
            browser.call('Input.dispatchKeyEvent', {'type': kind, 'key': 'Tab', 'code': 'Tab', 'windowsVirtualKeyCode': 9})
    assert found, 'P action not reached through actual Tab'
    result = browser.evaluate('''(()=>{const e=document.activeElement,r=e.getBoundingClientRect(),
      content=document.querySelector('#ees-work-content'),c=content.getBoundingClientRect(),
      table=document.querySelector('.ew-work-stage-table'),t=table.getBoundingClientRect(),s=getComputedStyle(table);
      return {viewport:[innerWidth,innerHeight],dark:document.documentElement.classList.contains('dark'),
        title:document.querySelector('#ees-work-panel .ew-title').textContent,
        actionCount:document.querySelectorAll('.ew-work-action-region').length,action:r.toJSON(),disabled:e.disabled,
        actionVisible:r.x>=0&&r.right<=innerWidth&&r.y>=0&&r.bottom<=innerHeight,
        documentWidth:document.documentElement.scrollWidth,contentClient:content.clientWidth,contentScroll:content.scrollWidth,
        stageTable:t.toJSON(),tableWithinContent:t.x>=c.x&&t.right<=c.right+1,
        tableColor:s.color,tableBackground:s.backgroundColor,tableFontSize:s.fontSize,
        composerClient:document.querySelector('#message-input-container').clientWidth,
        composerScroll:document.querySelector('#message-input-container').scrollWidth};})()''')
    assert result['dark'] and result['actionCount'] == 1 and result['actionVisible'] and not result['disabled'], result
    assert result['documentWidth'] <= 1367 and result['contentScroll'] <= result['contentClient'] + 1, result
    assert result['tableWithinContent'] and result['composerScroll'] <= result['composerClient'] + 1, result
    shot('visual-p-dark-keyboard-1366')
    capture('p-dark-1366', None, [(1366, 768, 'responsive')])
    return {'ok': True, **result, 'boundary': 'Actual existing theme preference/reload and keyboard focus; no repeated P execution'}


def layout_gate(*, browser, click, wait, shot, capture):
    """Only the final footer/spacing delta: real Tab focus and small viewports."""
    results = []
    for width, height in ((1536, 960), (1366, 768), (1048, 768)):
        browser.call('Emulation.setDeviceMetricsOverride', {'width': width, 'height': height,
                     'deviceScaleFactor': 1, 'mobile': False})
        wait('!!document.querySelector(".ew-work-scope-action button")')
        click('#ees-work-panel .ew-title')
        found = False
        for _ in range(100):
            if browser.evaluate('document.activeElement?.matches(".ew-work-scope-action button")'):
                found = True
                break
            for kind in ('keyDown', 'keyUp'):
                browser.call('Input.dispatchKeyEvent', {'type': kind, 'key': 'Tab', 'code': 'Tab', 'windowsVirtualKeyCode': 9})
        assert found, 'Scope action not reached through actual Tab'
        geometry = browser.evaluate('''(()=>{const e=document.activeElement,r=e.getBoundingClientRect();return {
          text:e.innerText,rect:r.toJSON(),disabled:e.disabled,visible:r.x>=0&&r.right<=innerWidth&&r.y>=0&&r.bottom<=innerHeight,
          actionCount:document.querySelectorAll('.ew-work-action-region').length,
          documentWidth:document.documentElement.scrollWidth,viewport:innerWidth,
          composerClient:document.querySelector('#message-input-container')?.clientWidth,
          composerScroll:document.querySelector('#message-input-container')?.scrollWidth};})()''')
        assert geometry['visible'] and not geometry['disabled'], geometry
        assert geometry['actionCount'] == 1 and geometry['documentWidth'] <= width + 1, geometry
        assert geometry['composerScroll'] <= geometry['composerClient'] + 1, geometry
        shot('visual-scope-keyboard-' + str(width))
        results.append({'viewport': [width, height], **geometry})
        capture('t-scope-layout-' + str(width), None, [(width, height, 'responsive')])
    return {'ok': True, 'checks': results,
            'boundary': 'Actual keyboard focus and rendering only; no repeat scope execution'}


def authoring_gate(*, browser, click, wait, shot):
    """Read-only arrival through existing controls; no draft edits or publish."""
    browser.call('Emulation.setDeviceMetricsOverride', {'width': 1920, 'height': 1048,
                 'deviceScaleFactor': 1, 'mobile': False})
    wait('!!document.querySelector("#ees-work-authoring-open")?.getClientRects().length && !document.querySelector("#ees-work-authoring-open").disabled')
    browser.events.clear()
    click('#ees-work-authoring-open')
    wait('new URLSearchParams(location.search).get("ees")==="workflow" && document.querySelector("#ees-work-node-form input[name=name]")?.value === "신규 공장 횡전개"')
    selected = browser.evaluate('({url:location.pathname+location.search,name:document.querySelector("#ees-work-node-form input[name=name]").value,process:document.querySelector("#ees-work-manage-process")?.value,owner:document.querySelector("#ees-work-manage-system")?.value})')
    assert selected['owner'] == 'UNASSIGNED', selected
    writes = [event for event in browser.events if event.get('method') == 'Network.requestWillBeSent'
              and event['params']['request'].get('method') not in ('GET', 'OPTIONS')
              and '/api/ees-work/authoring' in event['params']['request'].get('url', '')]
    assert not writes, 'Authoring entry unexpectedly wrote an authoring action'
    shot('visual-current-process-authoring-arrival')
    click('button[aria-label="사용자 메뉴"],button[aria-label="User menu"]')
    wait("!!document.querySelector('a[href=\"/workspace\"]')?.getClientRects().length")
    shot('visual-native-account-workspace-entry')
    click('a[href="/workspace"]')
    wait("location.pathname.startsWith('/workspace') && !!document.querySelector('#workspace-container') && !!document.querySelector('a[href=\"/workspace/models\"]')")
    shot('visual-native-workspace-preserved')
    return {'ok': True, 'current_process': selected, 'authoring_writes': 0,
            'native_account_and_workspace_controls': True,
            'boundary': 'Actual current published P entry and existing Native Workspace navigation only; no edits or publishing'}


def interaction_gate(*, out, browser, click, wait, shot, capture, api, current,
                     provider, base, chat_id, only_file=False):
    evidence = {'checks': [], 'boundary': 'Official app; physical input; temporary synthetic files/data only'}

    def key(value, code=None, modifiers=0):
        virtual_key = {'Tab': 9, 'Escape': 27, 'Home': 36, 'End': 35}.get(value,
                       ord(value.upper()) if len(value) == 1 else 0)
        for kind in ('keyDown', 'keyUp'):
            browser.call('Input.dispatchKeyEvent', {'type': kind, 'key': value,
                         'code': code or value, 'modifiers': modifiers, 'windowsVirtualKeyCode': virtual_key})

    def tab_to(selector, maximum=70):
        for _ in range(maximum):
            if browser.evaluate('document.activeElement?.matches(' + json.dumps(selector) + ')'):
                return
            key('Tab')
        raise AssertionError('Control not reached through actual Tab: ' + selector)

    def note(name, **values):
        evidence['checks'].append({'name': name, **values})
        (out/'interaction-result.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')

    def reload_page():
        browser.events.clear()
        browser.call('Page.reload')
        deadline = time.monotonic() + 15
        while not any(event.get('method') == 'Page.loadEventFired' for event in browser.events):
            browser.events.append(browser.receive(deadline))

    def composer_counts():
        return browser.evaluate('''(()=>({send:document.querySelectorAll('#send-message-button').length,
          disabled:document.querySelector('#send-message-button')?.disabled,
          voice:document.querySelectorAll('.ees-native-voice-menu').length}))()''')

    def click_text(text, within='body'):
        # Native portal menus can start additional fallback-font loads. The
        # menu is already on screen: require a stable physical hit target, not
        # a global fonts.ready promise for unrelated document text. Resolve the
        # observed label each frame because Native replaces its opening portal.
        geometry = browser.evaluate('''new Promise(resolve=>{let previous='',same=0;const end=performance.now()+3000;
          function inspect(){const root=document.querySelector(''' + json.dumps(within) + '''),
            e=[...root.querySelectorAll('button,[role="menuitem"],a,summary')].find(e=>e.getClientRects().length&&
              (e.innerText.trim()===''' + json.dumps(text) + '''||e.getAttribute('aria-label')===''' + json.dumps(text) + ''')),r=e?.getBoundingClientRect();
            if(!r){if(performance.now()>end)return resolve({stable:false,hit:false});requestAnimationFrame(inspect);return;}
            const x=r.x+r.width/2,y=r.y+r.height/2,
            value=[r.x,r.y,r.width,r.height].join(),hit=e.contains(document.elementFromPoint(x,y));
            same=value===previous&&hit?same+1:0;previous=value;
            if(same>=8||performance.now()>end)return resolve({x,y,stable:same>=8,hit,
              fontStatus:document.fonts.status,fontFamily:getComputedStyle(e).fontFamily});
            requestAnimationFrame(inspect);}inspect();})''')
        assert geometry['stable'] and geometry['hit'], (text, geometry)
        for kind in ('mousePressed', 'mouseReleased'):
            browser.call('Input.dispatchMouseEvent', {'type': kind, 'x': geometry['x'], 'y': geometry['y'],
                         'button': 'left', 'clickCount': 1})
        note('Physical Native portal control selected', control=text, geometry=geometry)

    try:
        if not only_file:
            sidebar_before = browser.evaluate('({width:document.querySelector("#sidebar").getBoundingClientRect().width,saved:localStorage.getItem("sidebarWidth"),open:localStorage.getItem("sidebar")})')
            assert abs(sidebar_before['width'] - 312) < 1, sidebar_before
            browser.evaluate('localStorage.setItem("sidebarWidth","360");localStorage.setItem("sidebar","false")')
            reload_page()
            wait('!!document.querySelector("#chat-input.ProseMirror") && document.querySelector("#sidebar")?.getBoundingClientRect().width < 100')
            assert browser.evaluate('localStorage.getItem("sidebarWidth")==="360" && localStorage.getItem("sidebar")==="false"')
            click('button[aria-label="사이드바 열기"],button[aria-label="Open sidebar"]')
            wait('Math.abs(document.querySelector("#sidebar").getBoundingClientRect().width-360)<1')
            shot('visual-native-saved-sidebar360')
            note('Default sidebar is 312px; isolated pre-existing saved 360px/closed preferences survive reload and actual reopening')
            browser.evaluate('localStorage.setItem("sidebarWidth","312");localStorage.setItem("sidebar","true")')
            reload_page()
            wait('!!document.querySelector("#chat-input.ProseMirror") && Math.abs(document.querySelector("#sidebar")?.getBoundingClientRect().width-312)<1')
            if not browser.evaluate('!!document.querySelector("#ees-work-panel")?.getClientRects().length'):
                click('#ees-work-context-open')
            # Retain the completed job, then vary only the real viewport.
            click('#ees-work-content [data-work-job="db-j"] [data-action="select"]')
            wait('document.querySelector("#ees-work-panel .ew-title")?.textContent === "DB 연결 확인"')
            for width, height in ((1536, 960), (1366, 768)):
                capture('j-complete-' + str(width), None, [(width, height, 'responsive')])
            browser.call('Emulation.setDeviceMetricsOverride', {'width': 1366, 'height': 768,
                         'deviceScaleFactor': 1, 'mobile': False})
            wait('document.documentElement.scrollWidth <= innerWidth + 1')
            note('1366 viewport has no document horizontal overflow')

            browser.call('Emulation.setDeviceMetricsOverride', {'width': 1048, 'height': 768,
                         'deviceScaleFactor': 1, 'mobile': False})
            wait('document.querySelector("#ees-work-resizer")?.hidden')
            assert browser.evaluate('getComputedStyle(document.querySelector("#ees-work-resizer")).display==="none"')
            for _ in range(20):
                key('Tab')
                assert not browser.evaluate('document.activeElement?.id==="ees-work-resizer"')
            capture('narrow-hidden-separator', None, [(1048, 768, 'responsive')])
            note('Narrow hidden separator has display none and is absent from 20 actual Tab steps')

            # Home/End are the existing keyboard splitter contract, not CSS widths.
            tab_to('#ees-work-resizer')
            key('Home')
            wait('Math.abs(document.querySelector("#ees-work-panel").getBoundingClientRect().width-340)<1')
            capture('j-complete-panel340', None, [(1366, 768, 'responsive')])
            click('#ees-work-close')
            wait('!document.querySelector("#ees-work-panel")?.getClientRects().length')
            click('#ees-work-context-open')
            wait('Math.abs(document.querySelector("#ees-work-panel").getBoundingClientRect().width-340)<1')
            note('Keyboard 340px resize and close/reopen preserve selected completed job',
                 status=current()['case']['jobs']['db-j']['status'])
            tab_to('#ees-work-resizer')
            key('End')

            # Real disclosure dialog, natural scroll and focus containment.
            click('[data-action="work_detail"][data-detail-tab="config"]')
            wait('!!document.querySelector("#ees-work-dialog")?.open')
            dialog = browser.evaluate('''(()=>{const e=document.querySelector('#ees-work-dialog'),r=e.getBoundingClientRect();
              const s=getComputedStyle(e);return {rect:r.toJSON(),fontSize:s.fontSize,lineHeight:s.lineHeight,
                overflowY:s.overflowY,scrollHeight:e.scrollHeight,clientHeight:e.clientHeight};})()''')
            shot('visual-detail-config')
            for _ in range(15):
                key('Tab')
                assert browser.evaluate('document.querySelector("#ees-work-dialog").contains(document.activeElement)')
            key('Escape')
            wait('!document.querySelector("#ees-work-dialog")?.open')
            note('Detail geometry and 15 actual Tab steps remain contained; Escape closes', geometry=dialog,
                 focus_restored=browser.evaluate('document.activeElement?.matches("[data-action=work_detail]")'))

            # Empty/input/empty lifecycle must never duplicate Native send controls.
            empty = composer_counts()
            assert empty == {'send': 1, 'disabled': True, 'voice': 1}, empty
            click('.ees-native-voice-menu > summary')
            wait('document.querySelector(".ees-native-voice-menu")?.open')
            assert browser.evaluate('!!document.querySelector(".ees-native-voice-menu button")?.getClientRects().length')
            key('Escape')
            wait('!document.querySelector(".ees-native-voice-menu")?.open')
            note('Original Native voice entry remains reachable; no microphone activation')

            click('#model-selector-model-button')
            wait('!!document.querySelector("#model-search-input")?.getClientRects().length')
            shot('visual-native-model-menu')
            key('Escape')
            wait('!document.querySelector("#model-search-input")?.getClientRects().length')
            click('#integration-menu-button')
            wait('[...document.querySelectorAll("body *")].some(e=>e.getClientRects().length && e.innerText?.trim()==="코드 인터프리터")')
            shot('visual-native-integration-menu')
            key('Escape')
            note('Original Native model and integration menus open with actual controls')

            provider.native_content = ('긴 본문 줄바꿈과 대화 스크롤 확인을 위한 합성 응답입니다. ' * 90)
            long_question = '긴 입력 표시 확인: ' + ('대상설비와작업조건을확인합니다 ' * 45)
            before_models = len(provider.models)
            click('#chat-input')
            browser.call('Input.insertText', {'text': long_question})
            wait('!document.querySelector("#send-message-button")?.disabled')
            filled = composer_counts()
            assert filled == {'send': 1, 'disabled': False, 'voice': 0}, filled
            shot('visual-native-long-input')
            click('#send-message-button')
            wait('document.querySelector("#chat-container")?.innerText.includes("긴 본문 줄바꿈과 대화 스크롤 확인을 위한 합성 응답입니다.")')
            wait('document.querySelector("#send-message-button")?.disabled')
            assert len(provider.models) == before_models + 1
            assert composer_counts() == empty
            capture('native-long-body', None, [(1366, 768, 'responsive')])
            note('Actual long Native input/send/answer preserves single send and voice lifecycle', model_calls=1)

            # Use the existing Native local theme preference consumed by index.html
            # on reload, plus its stored UI setting. Never mutate document classes
            # or styles; this is a temporary user's ordinary preference.
            api('/api/v1/users/user/settings/update', {'ui': {'language': 'ko-KR', 'theme': 'dark',
                'showChangelog': False, 'models': ['c3-synthetic-model']}})
            browser.evaluate('localStorage.setItem("theme","dark")')
            reload_page()
            wait('!!document.querySelector("#chat-input.ProseMirror") && document.documentElement.classList.contains("dark")')
            if not browser.evaluate('!!document.querySelector("#ees-work-panel")?.getClientRects().length'):
                click('#ees-work-context-open')
            capture('dark-j-complete', None, [(1366, 768, 'responsive')])
            note('Existing Native local dark preference and real reload preserve chat/work state')

            before_edit = current()['case']['jobs']['db-j']
            click('.ew-work-edit > summary')
            wait('document.querySelectorAll(".ew-work-action-region").length===1 && !!document.querySelector(".ew-work-edit[open] > .ew-work-action-region")')
            shot('visual-completed-edit-open')
            click('.ew-work-edit > summary')
            wait('!document.querySelector(".ew-work-edit")?.open && document.querySelectorAll(".ew-work-action-region").length===1 && !document.querySelector(".ew-work-edit > .ew-work-action-region")')
            click('.ew-work-edit > summary')
            wait('!!document.querySelector(".ew-work-edit[open] > .ew-work-action-region")')
            click('#ees-work-inputs input[name="db"]')
            key('a', 'KeyA', 2)
            browser.call('Input.insertText', {'text': '수정된 합성 대상 · 기록 보존 확인'})
            wait('document.querySelector("#ees-work-inputs input[name=db]").value === "수정된 합성 대상 · 기록 보존 확인"')
            wait('!document.querySelector("#ees-work-inputs-save").disabled')
            click('#ees-work-inputs-save')
            wait('!document.querySelector("#ees-work-panel")?.matches("[aria-busy=true]")')
            after_edit = current()['case']['jobs']['db-j']
            assert after_edit['inputs']['db'] == '수정된 합성 대상 · 기록 보존 확인'
            assert after_edit['history'] == before_edit['history']
            assert after_edit['attempt'] == before_edit['attempt']
            note('Completed input edit moves one action region, closes/restores, reopens/saves and preserves prior attempts/history',
                 history_count=len(after_edit['history']), attempt=after_edit['attempt'])
        sample_file = out/'synthetic-native-upload.txt'
        sample_file.write_text('Synthetic attachment for isolated Native upload verification. No company data.\n', encoding='utf-8')
        browser.call('Page.setInterceptFileChooserDialog', {'enabled': True})
        browser.events.clear()
        click('#input-menu-button')
        click_text('파일 업로드')
        chooser = next((event for event in browser.events if event.get('method') == 'Page.fileChooserOpened'), None)
        deadline = time.monotonic() + 8
        while chooser is None:
            event = browser.receive(deadline)
            browser.events.append(event)
            if event.get('method') == 'Page.fileChooserOpened':
                chooser = event
        assert chooser['params']['mode'] == 'selectMultiple', chooser
        browser.call('DOM.setFileInputFiles', {'backendNodeId': chooser['params']['backendNodeId'],
                     'files': [str(sample_file.resolve())]})
        wait('document.querySelector("#message-input-container")?.innerText.includes("synthetic-native-upload.txt")')
        deadline = time.monotonic() + 12
        upload = None
        while upload is None:
            posts = {event['params']['requestId'] for event in browser.events
                     if event.get('method') == 'Network.requestWillBeSent'
                     and event['params']['request'].get('method') == 'POST'
                     and '/api/v1/files/' in event['params']['request'].get('url', '')}
            completed = {event['params']['requestId'] for event in browser.events
                         if event.get('method') == 'Network.loadingFinished'}
            upload = next((event['params'] for event in browser.events if event.get('method') == 'Network.responseReceived'
                           and event['params']['requestId'] in posts & completed), None)
            if upload is None:
                browser.events.append(browser.receive(deadline))
        assert upload['response']['status'] == 200, upload['response']['status']
        body = json.loads(browser.call('Network.getResponseBody', {'requestId': upload['requestId']})['body'])
        deadline = time.monotonic() + 12
        status = api('/api/v1/files/' + body['id'] + '/process/status')['status']
        while status not in ('completed', 'failed') and time.monotonic() < deadline:
            time.sleep(0.5)
            status = api('/api/v1/files/' + body['id'] + '/process/status')['status']
        assert status == 'completed', {'upload_status': status}
        content = api('/api/v1/files/' + body['id'] + '/data/content')['content']
        assert 'Synthetic attachment for isolated Native upload verification. No company data.' in content
        shot('visual-native-file-upload')
        note('Original Native chooser opens, uploads and processes synthetic text; read-only saved content matches',
             filename=sample_file.name, upload_http_status=200, processing_status=status,
             external_embedding_boundary='Only embedding vectors are loopback synthesis; Native upload/parser/storage remain real')
        browser.call('Page.setInterceptFileChooserDialog', {'enabled': False})
        # Complete the Native attachment contract through the same real composer.
        # The GETs below only observe persisted state; no save/completion API is
        # called by this harness.
        attachment_question = '이 합성 첨부 파일을 확인해 줘.'
        attachment_answer = '합성 첨부 응답: 공식 Native 파일 연결과 대화 저장을 확인했습니다.'
        provider.native_content = attachment_answer
        browser.events.clear()
        click('#chat-input')
        browser.call('Input.insertText', {'text': attachment_question})
        wait('document.querySelectorAll("#send-message-button").length===1 && !document.querySelector("#send-message-button").disabled')
        click('#send-message-button')
        wait('document.querySelector("#chat-container")?.innerText.includes(' + json.dumps(attachment_answer) + ') && document.querySelector("#chat-container")?.innerText.includes("synthetic-native-upload.txt")')
        wait('document.querySelector("#send-message-button")?.disabled')
        requests = [event['params'] for event in browser.events
                    if event.get('method') == 'Network.requestWillBeSent'
                    and event['params']['request'].get('method') == 'POST'
                    and event['params']['request'].get('url') == base + '/api/chat/completions']
        assert len(requests) == 1, {'native_attachment_send_requests': len(requests)}
        saved = api('/api/v1/chats/' + chat_id)['chat']['history']['messages']
        matching = [message for message in saved.values()
                    if message.get('role') == 'user' and message.get('content') == attachment_question]
        assert len(matching) == 1, {'saved_attachment_messages': len(matching)}
        attachment_message = matching[0]
        files = attachment_message.get('files', [])
        assert any(item.get('id') == body['id'] or item.get('file', {}).get('id') == body['id'] for item in files), files
        shot('visual-native-attachment-message')
        reload_page()
        wait('document.querySelector("#chat-container")?.innerText.includes(' + json.dumps(attachment_answer) + ') && document.querySelector("#chat-container")?.innerText.includes("synthetic-native-upload.txt")')
        restored = api('/api/v1/chats/' + chat_id)['chat']['history']['messages']
        assert restored[attachment_message['id']]['files'] == files
        shot('visual-native-attachment-restored')
        note('Actual Native attached send saves the original file ID, displays answer/file and restores both after reload',
             native_send_requests=1, chat_id=chat_id, message_id=attachment_message['id'], file_id=body['id'],
             boundary='Only external model/embedding responses are loopback synthesis; Native chooser, parsing, retrieval, send and persistence are real')
        evidence['ok'] = True
        return evidence
    finally:
        (out/'interaction-result.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
