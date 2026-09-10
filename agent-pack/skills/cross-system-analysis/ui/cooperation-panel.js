/* Embedded by ApplyDemo in the two analysis Tools. eesPanelUpdate is data,
 * supplied by the caller; this fixed script never evaluates model output. */
try {
  const update = eesPanelUpdate;
  const fail = code => ({ok: false, error: {code}});
  const phases = new Set(['requested', 'analyzing', 'querying', 'completed', 'partial', 'failed', 'cancelled']);
  if (!update || update.version !== 1 || !['specialist', 'comparison'].includes(update.kind)
      || !['chat_id', 'message_id', 'call_id', 'batch_id'].every(key => typeof update[key] === 'string' && update[key].length > 0)
      || !Number.isSafeInteger(update.seq) || update.seq < 0 || !phases.has(update.phase)
      || (update.kind === 'specialist' && !['EMS', 'APC', 'FDC'].includes(update.system))) return fail('invalid_panel_event');
  const route = chat => '/c/' + encodeURIComponent(chat);
  const getLayout = () => {
    const anchor = document.querySelector('#chat-container #chat-pane'), column = anchor?.parentElement, row = column?.parentElement;
    const controls = column?.querySelector('nav button[aria-label="Controls"]'), wrapper = controls?.parentElement;
    const toolbar = wrapper?.parentElement || column?.querySelector('nav .flex-none.items-center.gap-2.self-center');
    return row?.isConnected && toolbar?.isConnected && getComputedStyle(row).display === 'flex'
      ? {anchor, column, row, toolbar, wrapper} : null;
  };
  if (location.pathname !== route(update.chat_id)) {
    window.__eesCooperationV1?.sync();
    // Known late calls may update their own in-memory history, never another chat.
    window.__eesCooperationV1?.receive(update, false);
    return fail('inactive_chat');
  }
  if (!getLayout()) return fail('unsupported_layout');
  if (!window.__eesCooperationV1) {
    const chats = new Map();
    let current = null, disposed = false;
    const element = (tag, text, className) => {
      const node = document.createElement(tag);
      if (text !== undefined) node.textContent = String(text);
      if (className) node.className = className;
      return node;
    };
    const statusText = phase => ({requested: '요청 전달 중', analyzing: '분석 중', querying: '자료 조회 중', completed: '회신 완료', partial: '부분 회신', failed: '실패', cancelled: '취소됨'}[phase] || '상태 미확인');
    const callStatus = call => call.stale ? '최신 상태 미확인' : statusText(call.phase);
    const number = value => value === null || value === undefined ? '미확인' : String(value);
    const text = value => value === null || value === undefined || value === '' ? '미지정' : Array.isArray(value) ? value.join(', ') || '없음' : String(value);
    const labels = {dataset: '시연 자료', group_by: '비교 단위', equipment_id: '설비', recipe_id: '레시피', event_id: '사건', event_ids: '사건', system: '분야', detailed: '상세 조회', detail: '상세 조회'};
    const descriptions = {planned_start: '계획 기동', maintenance: '정비 후 재개', overall: '전체', equipment_id: '설비별', recipe_id: '레시피별', equipment_recipe: '설비·레시피별'};
    const argumentsText = values => Object.entries(values || {}).filter(([, value]) => value !== '' && value !== undefined && value !== null)
      .map(([key, value]) => (labels[key] || key) + ': ' + (descriptions[value] || text(value))).join(' · ') || '별도 조건 없음';
    const create = chatId => {
      const messages = new Map(), cardNodes = new Map(), expanded = new Set(), evidenceOpen = new Set();
      let selectedMessage = null, selectedCall = null, latestMessage = null, wantsOpen = true, attached = false, autoOpenRequested = false;
      let layout = null, originalMinWidth, panelWidth = null, maximumWidth = 800, drag = null;
      const host = element('aside'); host.id = 'ees-cooperation-panel'; host.setAttribute('aria-label', '협업 과정');
      host.style.cssText = 'flex:0 0 480px;width:480px;min-width:0;height:100%;min-height:0;overflow:hidden;box-sizing:border-box;z-index:30;';
      const shadow = host.attachShadow({mode: 'open'});
      // This template is constant. Requests, replies and results use textContent.
      shadow.innerHTML = `<style>
        :host{--bg:light-dark(#fff,#191b1f);--soft:light-dark(#f6f7f9,#22252a);--ink:light-dark(#202630,#ebedf2);--muted:light-dark(#646d7a,#a9b1bf);--line:light-dark(#dce1e8,#3b424d);--blue:light-dark(#315e9e,#a4c6ff);--blue-bg:light-dark(#edf3ff,#25364f);--green:light-dark(#35664e,#abd3bb);--green-bg:light-dark(#edf6f0,#263c30);--warn:light-dark(#8a4d18,#edbd8c);font-family:system-ui,-apple-system,'Segoe UI',sans-serif;font-size:13px;color:var(--ink);line-height:1.6}
        *{box-sizing:border-box}[hidden]{display:none!important}button,select{font:inherit;color:inherit}button{cursor:pointer}button:focus-visible,select:focus-visible,summary:focus-visible{outline:2px solid var(--blue);outline-offset:3px}button{border:1px solid var(--line);background:var(--bg);border-radius:8px;padding:6px 10px}h2,h3,p{margin:0}h2{font-size:16px;font-weight:600}h3{font-size:14px;font-weight:600}.frame{height:100%;display:flex;flex-direction:column;background:var(--soft);border-left:1px solid var(--line)}header{padding:17px 18px 13px;background:var(--bg);border-bottom:1px solid var(--line)}.heading,.node-heading{display:flex;align-items:center;justify-content:space-between;gap:8px}.muted{color:var(--muted);font-size:12px}.scroll{overflow:auto;padding:18px;flex:1;min-height:0;overscroll-behavior:contain}.node{border:1px solid var(--line);border-radius:11px;padding:12px 14px;background:var(--bg)}.node p{margin-top:4px}.node-label{font-size:13px;font-weight:600}.line{width:1px;height:21px;background:var(--line);margin:0 auto}.batch{margin:0 0 10px}.batch-caption{text-align:center;margin:0 0 8px;color:var(--muted);font-size:11px}.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.cards[data-count="1"]{grid-template-columns:1fr}.cards[data-count="2"]{grid-template-columns:repeat(2,minmax(0,1fr))}.card{padding:12px 5px;display:flex;flex-direction:column;align-items:center;gap:5px;min-width:0;border-radius:10px}.card[aria-pressed="true"]{border-color:var(--blue);background:var(--blue-bg)}.name{font-size:15px;font-weight:600}.pill{font-size:11px;border-radius:5px;padding:2px 5px;background:var(--blue-bg);color:var(--blue)}.pill[data-phase="completed"]{background:var(--green-bg);color:var(--green)}.pill[data-phase="failed"],.pill[data-phase="partial"],.pill[data-phase="cancelled"]{color:var(--warn);background:var(--soft)}.join{margin-bottom:10px}.comparison{width:100%;text-align:left;margin-top:8px}.comparison[aria-pressed="true"]{border-color:var(--blue);background:var(--blue-bg)}.detail{margin-top:20px;padding-top:17px;border-top:1px solid var(--line)}.detail>p{margin-top:5px}dl{display:grid;gap:14px;margin:16px 0 0}dt{font-size:12px;color:var(--muted);margin-bottom:4px}dd{margin:0;overflow-wrap:anywhere}.plain{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.75}.query{border:1px solid var(--line);background:var(--bg);padding:10px 12px;border-radius:8px;margin-top:8px}.query p{margin-top:3px}.notice{color:var(--warn);font-size:12px;margin:8px 0}.footnote{color:var(--muted);font-size:11px;margin-top:20px}.history{margin-top:11px}.history select{display:block;width:100%;border:1px solid var(--line);background:var(--soft);border-radius:7px;padding:6px}.history label{font-size:11px;color:var(--muted)}.metrics{width:100%;border-collapse:collapse;margin:8px 0 15px;font-size:12px}.metrics th,.metrics td{text-align:left;vertical-align:top;border-bottom:1px solid var(--line);padding:6px 4px;overflow-wrap:anywhere}.metrics th{color:var(--muted);font-weight:400}.metric-title{margin-top:14px;font-weight:600}.expand{margin-top:8px;font-size:12px}details{margin-top:12px}summary{cursor:pointer;color:var(--blue)}.evidence{padding:8px 0;border-bottom:1px solid var(--line);overflow-wrap:anywhere}.truncate{display:-webkit-box;-webkit-line-clamp:6;-webkit-box-orient:vertical;overflow:hidden}.branch{height:11px;border-top:1px solid var(--line);margin:0 16.6%}.close{font-size:12px;white-space:nowrap}@media(pointer:coarse){button,select,summary{min-height:40px}}@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto}}
      </style>
      <section class="frame"><header><div class="heading"><h2>협업 과정</h2><button id="close" class="close" type="button" aria-label="협업 과정 접기">접기</button></div><p id="live" class="muted" role="status" aria-live="polite"></p><div id="history" class="history" hidden><label for="message-select">이 대화의 분석</label><select id="message-select"></select></div></header>
      <div id="scroll" class="scroll"><div class="node"><span class="node-label">EES 통합 Assistant</span><p id="assignment" class="muted"></p></div><div class="line" aria-hidden="true"></div><div id="batches"></div><div id="join" class="line join" aria-hidden="true"></div><div class="node"><span class="node-label">EES · 결과 연결</span><p id="synthesis" class="muted"></p><div id="comparisons"></div></div><section class="detail" aria-labelledby="detail-title"><h3 id="detail-title"></h3><p id="detail-status" class="muted"></p><div id="detail-body"></div></section><p class="footnote">합성 시연 자료 · 실제 요청·조회·회신을 표시합니다.<br>최종 해석과 제안은 대화 답변에서 확인하세요. 새로고침하면 이 패널 기록은 초기화됩니다.</p></div></section>`;
      const q = id => shadow.getElementById(id);
      const divider = element('div'); divider.id = 'ees-cooperation-resizer'; divider.tabIndex = 0;
      divider.style.cssText = 'flex:0 0 10px;width:10px;cursor:col-resize;touch-action:none;display:flex;align-items:center;justify-content:center;z-index:31;';
      Object.entries({role: 'separator', 'aria-label': '대화와 협업 과정 너비 조절', 'aria-orientation': 'vertical', 'aria-controls': host.id}).forEach(([key, value]) => divider.setAttribute(key, value));
      const grip = element('span'); grip.style.cssText = 'width:3px;height:36px;background:#8888;border-radius:2px;pointer-events:none;'; divider.append(grip);
      const slot = element('div'); slot.className = 'flex';
      const launcher = element('button', '협업'); launcher.id = 'ees-cooperation-toggle'; launcher.type = 'button';
      launcher.style.cssText = 'font:inherit;font-size:12px;border:1px solid #8885;border-radius:7px;padding:3px 7px;cursor:pointer;color:inherit;background:transparent;white-space:nowrap;';
      launcher.setAttribute('aria-controls', host.id); slot.append(launcher);
      const theme = () => { host.style.colorScheme = document.documentElement.classList.contains('dark') ? 'dark' : 'light'; };
      const finishDrag = event => {
        if (!drag || (event && event.pointerId !== drag.id)) return;
        const previous = drag; drag = null;
        if (divider.hasPointerCapture(previous.id)) divider.releasePointerCapture(previous.id);
        document.body.style.userSelect = previous.selection; document.body.style.cursor = previous.cursor;
      };
      const setWidth = width => {
        panelWidth = Math.round(Math.max(350, Math.min(maximumWidth, width)));
        host.style.width = panelWidth + 'px'; host.style.flexBasis = panelWidth + 'px';
        divider.setAttribute('aria-valuenow', String(panelWidth)); divider.setAttribute('aria-valuetext', panelWidth + '픽셀');
      };
      const resize = () => {
        if (!host.isConnected || !layout) return;
        const occupied = Array.from(layout.row.children).filter(node => ![layout.column, host, divider].includes(node))
          .reduce((sum, node) => sum + (['fixed', 'absolute'].includes(getComputedStyle(node).position) ? 0 : node.getBoundingClientRect().width), 0);
        const available = layout.row.clientWidth - occupied, narrow = window.innerWidth < 900 || available < 720;
        divider.hidden = narrow; divider.style.display = narrow ? 'none' : 'flex';
        host.style.position = narrow ? 'fixed' : 'relative'; host.style.inset = narrow ? '0 0 0 auto' : 'auto'; host.style.zIndex = narrow ? '60' : '30';
        if (narrow) { finishDrag(); host.style.width = 'min(100%,480px)'; }
        else {
          maximumWidth = Math.floor(Math.min(800, available - 370));
          divider.setAttribute('aria-valuemin', '350'); divider.setAttribute('aria-valuemax', String(maximumWidth));
          setWidth(panelWidth === null ? Math.min(480, available * .44) : panelWidth);
        }
      };
      const resizeObserver = new ResizeObserver(resize);
      const observeLayout = () => {
        resizeObserver.disconnect();
        if (!host.isConnected || !layout) return;
        resizeObserver.observe(layout.row);
        Array.from(layout.row.children).filter(node => node !== host && node !== divider).forEach(node => resizeObserver.observe(node));
      };
      const launcherState = () => {
        launcher.setAttribute('aria-expanded', String(wantsOpen));
        launcher.setAttribute('aria-label', wantsOpen ? '협업 과정 접기' : '협업 과정 열기');
        launcher.title = wantsOpen ? '협업 과정 접기' : '협업 과정 열기';
        launcher.style.background = wantsOpen ? '#8882' : 'transparent';
      };
      const hide = () => {
        finishDrag(); resizeObserver.disconnect(); window.removeEventListener('resize', resize);
        host.remove(); divider.remove(); if (attached) layout.column.style.minWidth = originalMinWidth;
      };
      const open = (value = true, explicit = false, focusOnOpen = explicit) => {
        wantsOpen = value; launcherState();
        if (!value) { hide(); return; }
        if (!attached) return;
        // WO's public open() ignores arguments; its real close button preserves draft state.
        const wo = document.getElementById('ees-wo-demo-panel');
        if (wo?.isConnected) {
          if (!explicit) { wantsOpen = false; launcherState(); return; }
          wo.shadowRoot?.getElementById('close')?.click();
          if (wo.isConnected) { wantsOpen = false; launcherState(); return; }
        }
        if (!host.isConnected) { layout.row.append(divider, host); observeLayout(); window.addEventListener('resize', resize); }
        layout.column.style.minWidth = '0'; resize(); theme();
        if (focusOnOpen && divider.hidden) q('close').focus({preventScroll: true});
      };
      const detailLine = (target, title, value, className) => {
        const wrapper = element('div'), dt = element('dt', title), dd = element('dd', value, className);
        wrapper.append(dt, dd); target.append(wrapper); return dd;
      };
      const table = (target, rows, header) => {
        const node = element('table', undefined, 'metrics');
        if (header) { const head = element('thead'), row = element('tr'); header.forEach(value => row.append(element('th', value))); head.append(row); node.append(head); }
        const body = element('tbody'); rows.forEach(values => { const row = element('tr'); values.forEach(value => row.append(element('td', value))); body.append(row); }); node.append(body); target.append(node);
      };
      const renderComparison = (target, call) => {
        const dl = element('dl'); target.append(dl); detailLine(dl, '비교 조건', argumentsText(call.arguments));
        const result = call.result;
        if (!result || result.ok !== true) { detailLine(dl, '계산 결과', call.phase === 'failed' ? '비교를 완료하지 못했습니다.' : '아직 계산 결과를 받지 못했습니다.'); return; }
        const calc = result.calculation || {};
        detailLine(dl, '판정 기준', [calc.conditions, calc.consecutive_samples == null ? null : calc.consecutive_samples + '개 연속 표본', calc.end].filter(Boolean).join(' · ') || '결과에 기준이 포함되지 않았습니다.');
        const summary = result.summary || {};
        table(target, [['대상 사건', number(summary.total_events) + '건'], ['확인 / 미확인 / 판정 불가', [summary.confirmed_events, summary.not_confirmed_events, summary.unassessable_events].map(number).join(' / ') + '건'], ['확인된 사건 평균', summary.mean_confirmed_minutes == null ? '계산 불가' : number(summary.mean_confirmed_minutes) + '분'], ['평균 분모', number(summary.mean_denominator) + '건']]);
        (result.comparisons || []).forEach(comparison => {
          target.append(element('p', argumentsText(comparison.conditions), 'metric-title'));
          const rows = Object.entries(comparison.groups || {}).map(([key, group]) => [descriptions[key] || key, group.mean_confirmed_minutes == null ? '계산 불가' : number(group.mean_confirmed_minutes) + '분', number(group.mean_denominator), number(group.not_confirmed_events), number(group.unassessable_events)]);
          table(target, rows, ['구분', '평균', '분모', '미확인', '판정 불가']);
          target.append(element('p', '정비 후 재개 − 계획 기동: ' + (comparison.maintenance_minus_planned_minutes == null ? '계산 불가' : number(comparison.maintenance_minus_planned_minutes) + '분'), 'muted'));
        });
        if (calc.mean_policy) target.append(element('p', calc.mean_policy, 'muted'));
        if (calc.missing_policy) target.append(element('p', calc.missing_policy, 'muted'));
        if (result.events?.length) {
          const details = element('details'), summaryNode = element('summary', '사건별 근거 ' + result.events.length + '건'); details.open = evidenceOpen.has(call.call_id);
          summaryNode.dataset.focusKey = 'evidence'; details.addEventListener('toggle', () => { if (details.open) evidenceOpen.add(call.call_id); else evidenceOpen.delete(call.call_id); }); details.append(summaryNode);
          result.events.forEach(event => {
            const row = element('div', undefined, 'evidence'); row.append(element('p', [event.event_id, event.equipment_id, event.recipe_id].filter(Boolean).join(' · ')));
            row.append(element('p', '생산 재개: ' + text(event.resumed_at) + ' · ' + ({confirmed: '확인됨', not_confirmed_within_window: '관측 시간 내 미확인', unassessable: '자료 부족으로 판정 불가'}[event.state] || '상태 미확인'), 'muted'));
            row.append(element('p', '확인 소요: ' + (event.confirmed_after_minutes == null ? '계산 불가' : number(event.confirmed_after_minutes) + '분') + ' · 누락 표본: APC ' + number(event.missing_samples?.APC) + ', FDC ' + number(event.missing_samples?.FDC), 'muted'));
            row.append(element('p', '근거: ' + text(event.evidence_record_ids), 'muted')); details.append(row);
          }); target.append(details);
        }
        if (result.message) target.append(element('p', result.message, 'notice'));
      };
      const renderDetail = call => {
        const target = q('detail-body'); target.replaceChildren();
        if (!call) { q('detail-title').textContent = '작업 상세'; q('detail-status').textContent = '확인할 작업을 선택하세요.'; return; }
        q('detail-title').textContent = call.kind === 'specialist' ? call.system + ' Assistant' : 'EES · 교차 비교';
        q('detail-status').textContent = call.stale ? '최신 진행 상태 미확인 · 마지막 확인: ' + statusText(call.phase) : call.kind === 'comparison' && call.phase === 'completed' ? '비교 완료' : statusText(call.phase);
        if (call.kind === 'comparison') renderComparison(target, call);
        else {
          const dl = element('dl'); target.append(dl);
          detailLine(dl, call.request?.kind === 'followup' ? '보완 요청' : '맡긴 질문', call.request?.question || '요청 내용이 전달되지 않았습니다.', 'plain');
          const queries = detailLine(dl, '확인한 자료', '');
          if (!call.queries?.length) queries.textContent = call.phase === 'requested' ? '아직 자료 조회를 시작하지 않았습니다.' : '기록된 자료 조회가 없습니다.';
          (call.queries || []).forEach(query => {
            const card = element('div', undefined, 'query');
            card.append(element('p', '조회 ' + number(query.index) + ' · ' + ({querying: '조회 중', completed: '조회 완료', failed: '조회 실패', cancelled: '조회 취소'}[query.status] || '상태 미확인')));
            card.append(element('p', argumentsText(query.arguments), 'muted'));
            if (query.record_count != null) card.append(element('p', '조회 결과 ' + number(query.record_count) + '건', 'muted'));
            if (query.event_ids?.length) card.append(element('p', '사건: ' + query.event_ids.join(', '), 'muted'));
            queries.append(card);
          });
          const analysis = typeof call.analysis === 'string' ? call.analysis : '';
          const reply = detailLine(dl, '전문가 회신', analysis || (['completed', 'partial'].includes(call.phase) ? '표시할 회신이 없습니다.' : '아직 회신을 받지 못했습니다.'), 'plain');
          if (analysis.length > 700) {
            const isExpanded = expanded.has(call.call_id); reply.className = 'plain' + (isExpanded ? '' : ' truncate');
            const button = element('button', isExpanded ? '회신 접기' : '회신 전체 보기', 'expand'); button.type = 'button'; button.dataset.focusKey = 'expand'; button.setAttribute('aria-expanded', String(isExpanded));
            button.addEventListener('click', () => { if (expanded.has(call.call_id)) expanded.delete(call.call_id); else expanded.add(call.call_id); render(); }); target.append(button);
          }
          if (call.analysis_truncated) target.append(element('p', '회신이 길어 끝부분 16,000자만 전달되었습니다. 전체 회신으로 간주하지 마세요.', 'notice'));
        }
        if (call.phase === 'partial') target.append(element('p', '일부 회신 또는 근거만 확보했습니다. 한계를 함께 확인하세요.', 'notice'));
        if (call.phase === 'failed' || call.phase === 'cancelled') target.append(element('p', call.phase === 'cancelled' ? '이 작업은 취소되었습니다. 다른 작업의 결과는 유지됩니다.' : '이 작업을 완료하지 못했습니다. 다른 작업의 결과는 유지됩니다.', 'notice'));
      };
      const render = () => {
        const message = messages.get(selectedMessage); if (!message) return;
        const focusKey = shadow.activeElement?.dataset?.focusKey, scrollTop = q('scroll').scrollTop;
        cardNodes.clear();
        const calls = Array.from(message.calls.values()), specialists = calls.filter(call => call.kind === 'specialist'), comparisons = calls.filter(call => call.kind === 'comparison');
        if (!message.calls.has(selectedCall)) selectedCall = calls[0]?.call_id || null;
        const done = specialists.filter(call => call.phase === 'completed').length, pending = specialists.filter(call => !call.stale && ['requested', 'analyzing', 'querying'].includes(call.phase)).length;
        const status = calls.some(call => call.stale) ? '대화 이동 중 진행 알림이 중단되어 최신 상태를 확인할 수 없습니다.' : pending ? '전문 분석 ' + pending + '건 진행 중 · 회신 완료 ' + done + '건' : specialists.length ? '전문 분석 종료 · 회신 완료 ' + done + '건 · 작업별 상태를 확인하세요.' : 'EES의 교차 비교를 표시합니다.';
        if (q('live').textContent !== status) q('live').textContent = status;
        q('assignment').textContent = specialists.length ? [...new Set(specialists.map(call => call.system))].join(' · ') + '에 분석을 요청했습니다. 카드를 눌러 질문과 회신을 확인하세요.' : '전달된 비교 조건으로 자료를 연결합니다.';
        const batches = new Map(); specialists.forEach(call => { if (!batches.has(call.batch_id)) batches.set(call.batch_id, []); batches.get(call.batch_id).push(call); });
        q('batches').replaceChildren();
        batches.forEach(batch => {
          const section = element('section', undefined, 'batch'), cards = element('div', undefined, 'cards'); cards.dataset.count = String(batch.length);
          if (new Set(batch.map(call => call.system)).size > 1) { section.append(element('p', '함께 요청한 전문 분석 · 병렬 분석 요청', 'batch-caption')); section.append(element('div', undefined, 'branch')); }
          else if (batch.some(call => call.request?.kind === 'followup')) section.append(element('p', '추가로 요청한 보완 분석', 'batch-caption'));
          batch.forEach(call => {
            const card = element('button', undefined, 'card'); card.type = 'button'; card.dataset.callId = call.call_id; card.dataset.focusKey = call.call_id;
            card.setAttribute('aria-pressed', String(selectedCall === call.call_id)); card.setAttribute('aria-label', call.system + ' Assistant · ' + callStatus(call));
            card.append(element('span', call.system, 'name')); const pill = element('span', callStatus(call), 'pill'); pill.dataset.phase = call.stale ? 'partial' : call.phase; card.append(pill);
            card.append(element('span', call.request?.kind === 'followup' ? '보완 분석' : '전문 분석', 'muted'));
            card.addEventListener('click', () => { selectedCall = call.call_id; render(); }); cards.append(card); cardNodes.set(call.call_id, card);
          }); section.append(cards); q('batches').append(section);
        });
        q('join').hidden = specialists.length === 0;
        q('synthesis').textContent = calls.some(call => call.stale) ? '일부 작업의 최신 상태가 확인되지 않았습니다. 대화 답변과 새로 받은 결과를 확인하세요.' : comparisons.some(call => ['requested', 'analyzing', 'querying'].includes(call.phase)) ? '전문 결과와 시연 자료를 교차 비교하고 있습니다.'
          : comparisons.some(call => call.phase === 'completed') ? '계산 결과를 받았습니다. 최종 해석은 대화 답변에서 확인하세요.'
          : specialists.some(call => typeof call.analysis === 'string' && call.analysis.trim()) ? '전문가가 작성한 내용을 받았습니다. 각 작업의 완료 여부와 한계를 함께 확인하세요.'
          : specialists.length && specialists.every(call => ['completed', 'partial', 'failed', 'cancelled'].includes(call.phase)) ? '전문 분석이 종료되었습니다. 확보한 내용과 한계를 각 작업에서 확인하세요.'
          : comparisons.length && comparisons.every(call => ['failed', 'cancelled'].includes(call.phase)) ? '교차 비교가 종료되었으나 계산 결과를 받지 못했습니다.' : '전문가 회신을 기다리고 있습니다.';
        q('comparisons').replaceChildren();
        comparisons.forEach((call, index) => {
          const button = element('button', undefined, 'comparison'); button.type = 'button'; button.dataset.callId = call.call_id; button.dataset.focusKey = call.call_id;
          button.setAttribute('aria-pressed', String(selectedCall === call.call_id));
          button.append(element('span', '교차 비교 ' + (index + 1) + ' · ' + (call.stale ? callStatus(call) : call.phase === 'completed' ? '비교 완료' : ['requested', 'analyzing', 'querying'].includes(call.phase) ? '비교 중' : statusText(call.phase))));
          button.append(element('p', argumentsText(call.arguments), 'muted')); button.addEventListener('click', () => { selectedCall = call.call_id; render(); }); q('comparisons').append(button); cardNodes.set(call.call_id, button);
        });
        const select = q('message-select'); select.replaceChildren(); q('history').hidden = messages.size < 2;
        let index = 0; messages.forEach((item, id) => { index += 1; const first = Array.from(item.calls.values())[0]; const label = first?.request?.question || '교차 비교'; const option = element('option', '분석 ' + index + (id === latestMessage ? ' · 최근' : '') + ' — ' + label.slice(0, 42)); option.value = id; select.append(option); }); select.value = selectedMessage;
        renderDetail(message.calls.get(selectedCall)); q('scroll').scrollTop = scrollTop;
        if (focusKey) { const node = cardNodes.get(focusKey) || (['expand', 'evidence'].includes(focusKey) ? q('detail-body').querySelector('[data-focus-key="' + focusKey + '"]') : null); node?.focus({preventScroll: true}); }
      };
      const receive = event => {
        let message = messages.get(event.message_id);
        if (!message) {
          message = {calls: new Map()}; messages.set(event.message_id, message);
          const candidate = document.getElementById('message-' + event.message_id), previous = document.getElementById('message-' + latestMessage);
          const appearsOlder = candidate && previous && Boolean(candidate.compareDocumentPosition(previous) & 4);
          if (!latestMessage || (event.phase === 'requested' && !appearsOlder)) {
            latestMessage = event.message_id; selectedMessage = event.message_id; selectedCall = null;
            autoOpenRequested = event.phase === 'requested' && !appearsOlder && location.pathname === route(chatId);
          }
        }
        const old = message.calls.get(event.call_id);
        if (old && (old.seq >= event.seq || old.kind !== event.kind || old.system !== event.system || old.batch_id !== event.batch_id)) return false;
        message.calls.set(event.call_id, {...event, stale: false});
        render();
        return true;
      };
      const detach = () => {
        if (location.pathname !== route(chatId)) {
          messages.forEach(message => message.calls.forEach(call => { if (['requested', 'analyzing', 'querying'].includes(call.phase)) call.stale = true; }));
          render();
        }
        hide(); slot.remove(); attached = false; layout = null;
      };
      const attach = nextLayout => {
        layout = nextLayout; originalMinWidth = layout.column.style.minWidth; attached = true;
        layout.toolbar.insertBefore(slot, layout.wrapper || null); launcherState(); theme(); if (wantsOpen) open();
      };
      const alive = () => attached && location.pathname === route(chatId) && layout.row.isConnected && document.querySelector('#chat-container #chat-pane') === layout.anchor && layout.anchor.parentElement === layout.column && layout.column.parentElement === layout.row && slot.parentElement === layout.toolbar && launcher.isConnected;
      divider.addEventListener('pointerdown', event => {
        if (divider.hidden || event.button !== 0 || event.isPrimary === false) return;
        finishDrag(); drag = {id: event.pointerId, x: event.clientX, width: panelWidth, selection: document.body.style.userSelect, cursor: document.body.style.cursor};
        document.body.style.userSelect = 'none'; document.body.style.cursor = 'col-resize';
        try { divider.setPointerCapture(event.pointerId); } catch (_) { finishDrag(); return; }
        divider.focus({preventScroll: true}); event.preventDefault();
      });
      divider.addEventListener('pointermove', event => { if (drag && drag.id === event.pointerId) setWidth(drag.width + drag.x - event.clientX); });
      ['pointerup', 'pointercancel', 'lostpointercapture'].forEach(type => divider.addEventListener(type, finishDrag));
      divider.addEventListener('keydown', event => {
        if (divider.hidden || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
        event.preventDefault(); setWidth(event.key === 'Home' ? 350 : event.key === 'End' ? maximumWidth : panelWidth + (event.key === 'ArrowLeft' ? 20 : -20));
      });
      divider.addEventListener('focus', () => { divider.style.outline = '2px solid #6b91d5'; });
      divider.addEventListener('blur', () => { divider.style.outline = ''; });
      q('close').addEventListener('click', () => { open(false); launcher.focus({preventScroll: true}); });
      launcher.addEventListener('click', () => open(!wantsOpen, true));
      shadow.addEventListener('keydown', event => { if (event.key === 'Escape') { open(false); launcher.focus({preventScroll: true}); } });
      q('message-select').addEventListener('change', () => { if (messages.has(q('message-select').value)) { selectedMessage = q('message-select').value; selectedCall = null; render(); } });
      return {messages, receive, attach, detach, alive, open, theme,
        activateRequested: () => { if (autoOpenRequested) { autoOpenRequested = false; open(true, true, false); } },
        refresh: records => {
          if (document.getElementById('ees-wo-demo-panel')?.isConnected && host.isConnected) open(false);
          if (host.isConnected && records.some(record => record.target === layout.row)) { observeLayout(); resize(); }
        }, pathname: route(chatId)};
    };
    const sync = records => {
      if (disposed) return;
      if (/^\/(auth|logout)(\/|$)/.test(location.pathname)) { destroy(); return; }
      const next = Array.from(chats.values()).find(chat => chat.pathname === location.pathname) || null;
      const layout = next ? getLayout() : null;
      if (current && (current !== next || !current.alive())) { current.detach(); current = null; }
      if (next && layout) { if (!current) { current = next; current.attach(layout); } else current.refresh(Array.isArray(records) ? records : []); }
    };
    const theme = () => current?.theme();
    const observer = new MutationObserver(sync), themeObserver = new MutationObserver(theme), navigation = window.navigation;
    const destroy = () => {
      if (disposed) return; disposed = true;
      observer.disconnect(); themeObserver.disconnect(); navigation?.removeEventListener('navigatesuccess', sync);
      window.removeEventListener('popstate', sync); window.removeEventListener('pagehide', destroy);
      chats.forEach(chat => chat.detach()); chats.clear(); current = null; delete window.__eesCooperationV1;
    };
    const receive = (event, allowNew = true) => {
      if (disposed) return false;
      let chat = chats.get(event.chat_id);
      if (!chat) { if (!allowNew) return false; chat = create(event.chat_id); chats.set(event.chat_id, chat); }
      if (!allowNew && !chat.messages.has(event.message_id)) return false;
      const accepted = chat.receive(event); sync(); if (allowNew) chat.activateRequested(); return accepted;
    };
    window.__eesCooperationV1 = {receive, sync, destroy};
    observer.observe(document.body, {childList: true, subtree: true});
    themeObserver.observe(document.documentElement, {attributes: true, attributeFilter: ['class']});
    window.addEventListener('popstate', sync); window.addEventListener('pagehide', destroy); navigation?.addEventListener('navigatesuccess', sync);
  }
  return {ok: true, updated: window.__eesCooperationV1.receive(update)};
} catch (_) {
  // Fixed code only: exception messages may contain request or reply content.
  return {ok: false, error: {code: 'panel_unavailable'}};
}
