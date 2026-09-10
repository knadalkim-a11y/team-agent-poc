/* Embedded by ApplyDemo in the two analysis Tools. eesPanelUpdate is data,
 * supplied by the caller; this fixed script never evaluates model output. */
try {
  const update = eesPanelUpdate;
  const fail = code => ({ok: false, error: {code}});
  const phases = new Set(['planned', 'running', 'awaiting_summary', 'requested', 'analyzing', 'querying', 'completed', 'partial', 'failed', 'cancelled']);
  if (!update || update.version !== 1 || !['plan', 'specialist', 'comparison'].includes(update.kind)
      || !['chat_id', 'message_id', 'call_id', 'batch_id'].every(key => typeof update[key] === 'string' && update[key].length > 0)
      || !Number.isSafeInteger(update.seq) || update.seq < 0 || !phases.has(update.phase)
      || (update.kind === 'specialist' && !['EMS', 'APC', 'FDC'].includes(update.system))
      || (update.kind === 'plan' && (!Array.isArray(update.steps) || update.steps.length > 24))) return fail('invalid_panel_event');
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
    const statusText = phase => ({planned: '계획 수립', pending: '대기', running: '진행 중', awaiting_summary: '분석 정리 중', requested: '요청 전달 중', analyzing: '분석 중', querying: '자료 조회 중', completed: '완료', partial: '일부 확인', failed: '실패', cancelled: '취소됨'}[phase] || '상태 미확인');
    const callStatus = call => call.stale ? '최신 상태 미확인' : statusText(call.phase);
    const number = value => value === null || value === undefined ? '미확인' : String(value);
    const text = value => value === null || value === undefined || value === '' ? '미지정' : Array.isArray(value) ? value.join(', ') || '없음' : String(value);
    const labels = {dataset: '시연 자료', group_by: '비교 단위', equipment_id: '설비', recipe_id: '레시피', event_id: '사건', event_ids: '사건', system: '분야', detailed: '상세 조회', detail: '상세 조회'};
    const descriptions = {sample_a: '조립 2라인 · 기본 시연', sample_b: '조립 2라인 · 다른 시연 사례', planned_start: '계획 기동', maintenance: '정비 후 재개', overall: '전체', equipment_id: '설비별', recipe_id: '레시피별', equipment_recipe: '설비·레시피별'};
    const argumentsText = values => Object.entries(values || {}).filter(([, value]) => value !== '' && value !== undefined && value !== null)
      .map(([key, value]) => (labels[key] || key) + ': ' + (descriptions[value] || text(value))).join(' · ') || '별도 조건 없음';
    // A small display-only Markdown subset. Never parse HTML, build links, or
    // evaluate content. Unsupported notation remains visible as ordinary text.
    const inline = (target, value) => {
      const pattern = /\*\*([^*\n]+)\*\*|`([^`\n]+)`/g;
      let offset = 0;
      for (const match of value.matchAll(pattern)) {
        if (match.index > offset) target.append(element('span', value.slice(offset, match.index)));
        target.append(element(match[1] === undefined ? 'code' : 'strong', match[1] ?? match[2]));
        offset = match.index + match[0].length;
      }
      if (offset < value.length) target.append(element('span', value.slice(offset)));
    };
    const readable = (target, value) => {
      const lines = value.replace(/\r\n?/g, '\n').split('\n');
      let paragraph = [], list = null, fenced = null;
      const flush = () => { if (paragraph.length) { const p = element('p'); inline(p, paragraph.join('\n')); target.append(p); paragraph = []; } };
      lines.forEach(line => {
        if (/^\s*```[\w-]*\s*$/.test(line)) {
          flush(); list = null;
          if (fenced) { target.append(element('pre', fenced.join('\n'))); fenced = null; }
          else fenced = [];
          return;
        }
        if (fenced) { fenced.push(line); return; }
        if (!line.trim()) { flush(); list = null; return; }
        const heading = line.match(/^\s{0,3}#{1,6}\s+(.+)$/) || line.match(/^\s*\*\*([^*]+)\*\*\s*[:：]?\s*$/);
        const item = line.match(/^\s*([-+*]|\d+[.)])\s+(.+)$/);
        if (heading) { flush(); list = null; const h = element('h4'); inline(h, heading[1]); target.append(h); }
        else if (item) {
          flush(); const ordered = /^\d/.test(item[1]), tag = ordered ? 'ol' : 'ul';
          if (!list || list.tagName.toLowerCase() !== tag) { list = element(tag); if (ordered) list.setAttribute('start', parseInt(item[1], 10)); target.append(list); }
          const li = element('li'); if (ordered) li.setAttribute('value', parseInt(item[1], 10)); inline(li, item[2]); list.append(li);
        } else { list = null; paragraph.push(line); }
      });
      flush(); if (fenced) target.append(element('pre', fenced.join('\n')));
    };
    const create = chatId => {
      const work = window.__eesWorkPanelV1;
      const messages = new Map(), cardNodes = new Map(), expanded = new Set(), disclosures = new Map();
      let selectedMessage = null, selectedCall = null, selectedStep = null, latestMessage = null, wantsOpen = true, attached = false, autoOpenRequested = false;
      let analysisScreen = 'summary', detailTab = 'summary', evidenceFilter = null, viewChosen = false;
      let layout = null, originalMinWidth, panelWidth = null, maximumWidth = 800, drag = null;
      let renderedDisclosures = [];
      const host = element('aside'); host.id = 'ees-cooperation-panel'; host.setAttribute('aria-label', '분석 업무 패널');
      host.style.cssText = 'flex:0 0 480px;width:480px;min-width:0;height:100%;min-height:0;overflow:hidden;box-sizing:border-box;z-index:30;';
      const shadow = host.attachShadow({mode: 'open'});
      // This template is constant. Requests, replies and results use textContent.
      shadow.innerHTML = `<style>
        :host{--bg:light-dark(#fff,#191b1f);--soft:light-dark(#f6f7f9,#22252a);--ink:light-dark(#202630,#ebedf2);--muted:light-dark(#646d7a,#a9b1bf);--line:light-dark(#dce1e8,#3b424d);--blue:light-dark(#315e9e,#a4c6ff);--blue-bg:light-dark(#edf3ff,#25364f);--green:light-dark(#35664e,#abd3bb);--green-bg:light-dark(#edf6f0,#263c30);--warn:light-dark(#8a4d18,#edbd8c);font-family:system-ui,-apple-system,'Segoe UI',sans-serif;font-size:13px;color:var(--ink);line-height:1.6}
        *{box-sizing:border-box}[hidden]{display:none!important}button,select{font:inherit;color:inherit}button:focus-visible,select:focus-visible,summary:focus-visible{outline:2px solid var(--blue);outline-offset:3px}button{cursor:pointer;border:1px solid var(--line);background:var(--bg);border-radius:8px;padding:6px 10px}h2,h3,p{margin:0}h2{font-size:16px;font-weight:600}h3{font-size:16px;font-weight:600}
        .frame{height:100%;display:flex;flex-direction:column;background:var(--soft);border-left:1px solid var(--line)}header{padding:17px 18px 13px;background:var(--bg);border-bottom:1px solid var(--line)}.heading{display:flex;align-items:center;justify-content:space-between;gap:8px}.muted{color:var(--muted);font-size:12px}.scroll{overflow:auto;padding:18px;flex:1;min-height:0;overscroll-behavior:contain}.close{font-size:12px;white-space:nowrap}
        .node{border:1px solid var(--line);border-radius:11px;padding:10px 12px;background:var(--bg)}.node p{margin-top:4px}.node-label{font-size:13px;font-weight:600}.line{width:1px;height:15px;background:var(--line);margin:0 auto}.join{margin-bottom:10px}.batch{margin-bottom:4px}.batch-caption{text-align:center;margin:0 0 8px;color:var(--muted);font-size:11px}.branch{height:11px;border-top:1px solid var(--line);margin:0 16.6%}
        .cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.cards[data-count="1"]{grid-template-columns:1fr}.cards[data-count="2"]{grid-template-columns:repeat(2,minmax(0,1fr))}.card{padding:10px 5px;display:flex;flex-direction:column;align-items:center;gap:5px;min-width:0;border-radius:10px}.card[aria-pressed="true"],.comparison[aria-pressed="true"]{border-color:var(--blue);background:var(--blue-bg)}.card .muted{font-size:11px}.name{font-size:15px;font-weight:600}
        .pill{font-size:11px;border-radius:5px;padding:2px 5px;background:var(--blue-bg);color:var(--blue)}.pill[data-phase="completed"]{background:var(--green-bg);color:var(--green)}.pill[data-phase="failed"],.pill[data-phase="partial"],.pill[data-phase="cancelled"]{color:var(--warn);background:var(--soft)}.comparison{width:100%;text-align:left;margin-top:8px}
        .detail{background:var(--bg);border:1px solid var(--line);border-radius:12px;padding:16px;margin-top:18px}.detail>p{margin-top:5px}.detail-section{margin-top:18px}.section-label{font-size:12px;font-weight:600;color:var(--muted);margin-bottom:8px}.question{border-left:3px solid var(--line);padding:6px 10px;font-size:12px;color:var(--muted)}
        dl{display:grid;gap:14px;margin:16px 0 0}dt{font-size:12px;color:var(--muted);margin-bottom:4px}dd{margin:0;overflow-wrap:anywhere}.plain{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.75}
        .reply{font-size:14px;line-height:1.8;overflow-wrap:anywhere}.reply>p{white-space:pre-wrap;margin:0 0 12px}.reply h4{font-size:14px;font-weight:650;margin:18px 0 8px;padding-bottom:5px;border-bottom:1px solid var(--line)}.reply h4:first-child{margin-top:0}.reply ul,.reply ol{padding-left:22px;margin:8px 0 14px}.reply li{padding-left:3px;margin:6px 0;white-space:pre-wrap}
        .reply code{font-family:ui-monospace,monospace;font-size:.92em;background:var(--soft);border-radius:4px;padding:1px 4px}.reply pre{white-space:pre-wrap;background:var(--soft);border:1px solid var(--line);border-radius:6px;padding:10px;font-size:12px}.reply.truncate{max-height:300px;overflow:hidden}.preview-label{font-size:11px;color:var(--muted);margin-bottom:8px}.expand{width:100%;padding:8px 12px;margin-top:10px;font-size:12px;color:var(--blue)}
        .disclosure{border-top:1px solid var(--line);padding-top:12px;margin-top:16px}.disclosure summary{cursor:pointer;color:var(--blue);font-size:12px;font-weight:600;line-height:1.6}.disclosure[open]>summary{margin-bottom:10px}.disclosure>dl{margin-top:8px}.query{border:1px solid var(--line);background:var(--soft);padding:10px 12px;border-radius:8px;margin-top:8px;font-size:12px}.query p{margin-top:3px}
        .metric-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:14px 0}.metric{background:var(--soft);border:1px solid var(--line);border-radius:8px;padding:10px 12px}.metric dt{font-size:11px}.metric dd{font-size:19px;font-weight:600;line-height:1.4}.metric dd.small-value{font-size:15px}
        .metrics{width:100%;border-collapse:collapse;margin:8px 0 15px;font-size:12px}.metrics th,.metrics td{text-align:left;vertical-align:top;border-bottom:1px solid var(--line);padding:6px 4px;overflow-wrap:anywhere}.metrics th{color:var(--muted);font-weight:400}.metric-title{margin-top:14px;font-size:12px;font-weight:600}.evidence{padding:8px 0;border-bottom:1px solid var(--line);overflow-wrap:anywhere}
        .notice{color:var(--warn);font-size:12px;background:var(--soft);border-left:3px solid var(--warn);padding:8px 10px;line-height:1.7;margin:8px 0}.footnote{color:var(--muted);font-size:11px;line-height:1.65;margin-top:16px}.history{margin-top:11px}.history select{display:block;width:100%;border:1px solid var(--line);background:var(--soft);border-radius:7px;padding:6px}.history label{font-size:11px;color:var(--muted)}
        .work-tabs,.view-tabs,.detail-tabs{display:flex;gap:6px;margin-top:14px;flex-wrap:wrap}.work-tabs button,.view-tabs button,.detail-tabs button{flex:1;white-space:nowrap;padding:8px}.work-tabs button[aria-selected="true"],.view-tabs button[aria-selected="true"],.detail-tabs button[aria-selected="true"]{background:var(--blue-bg);color:var(--blue);border-color:var(--blue)}button:disabled{cursor:default;opacity:.5}.headline{font-size:19px;line-height:1.5;letter-spacing:-.3px}.summary-card{padding:16px;border:1px solid var(--line);background:var(--bg);border-radius:12px;margin-bottom:12px}.summary-card>p{margin-top:8px}.action{padding-top:12px;border-top:1px solid var(--line);font-size:13px}.finding{display:block;width:100%;text-align:left;margin-top:8px;padding:12px;line-height:1.7}.step{display:grid;grid-template-columns:28px minmax(0,1fr) auto;align-items:start;gap:9px;width:100%;text-align:left;margin-top:8px;padding:12px;background:var(--bg)}.step[aria-pressed="true"]{border-color:var(--blue);background:var(--blue-bg)}.step-index{font-weight:600;color:var(--muted)}.step-name{font-weight:600}.step-meta{font-size:11px;color:var(--muted);margin-top:3px}.step-summary{font-size:12px;margin-top:6px}.rationale-block{margin-top:14px;border-left:2px solid var(--line);padding-left:12px}.rationale-block h4{font-size:12px;color:var(--muted);margin:0 0 5px}.rationale-block p{white-space:pre-wrap;overflow-wrap:anywhere}.chart{padding:14px;border:1px solid var(--line);border-radius:10px;background:var(--bg);margin-top:12px}.chart h4{margin:0 0 9px;font-size:13px}.chart-bar{display:grid;grid-template-columns:76px minmax(0,1fr) 64px;align-items:center;gap:8px;width:100%;border:0;background:transparent;padding:9px 0;text-align:left;font-size:12px}.bar-track{height:22px;background:var(--soft);border-radius:3px;overflow:hidden}.bar-fill{display:block;height:100%;background:var(--blue);border-radius:3px}.chart-bar[data-group="planned_start"] .bar-fill{opacity:.45}.chart-meta{font-size:11px;color:var(--muted);margin-top:6px}.detail-tabs{margin:12px 0}.execution-history{margin-top:16px}.execution-history>summary{cursor:pointer;color:var(--muted);font-size:12px}.compact-summary{font-size:14px;line-height:1.8;white-space:pre-wrap}.detail-data{margin-top:12px}.evidence-selected{border:1px solid var(--blue);border-radius:8px;padding:12px;margin-top:12px;background:var(--bg)}
        @media(pointer:coarse){button,select,summary{min-height:40px}}@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto}}
      </style>
      <section class="frame"><header><div class="heading"><h2>업무 패널</h2><button id="close" class="close" type="button" aria-label="업무 패널 닫기">닫기</button></div><nav id="work-tabs" class="work-tabs" aria-label="업무 화면"><button id="work-analysis" type="button" aria-selected="true">분석 과정</button><button id="work-equipment" type="button" disabled>설비 조회</button><button id="work-wo" type="button" disabled>WO 작성</button></nav><p id="live" class="muted" role="status" aria-live="polite"></p><div id="history" class="history" hidden><label for="message-select">이 대화의 분석</label><select id="message-select"></select></div><nav class="view-tabs" aria-label="분석 화면"><button id="view-summary" type="button" aria-selected="true">분석 요약</button><button id="view-plan" type="button" aria-selected="false">실행 계획</button></nav></header>
      <div id="scroll" class="scroll"><section id="summary-screen"><div class="summary-card"><h3 id="summary-title" class="headline"></h3><p id="summary-conclusion" class="compact-summary"></p><p id="summary-next" class="action" hidden></p><p id="summary-limits" class="notice" hidden></p></div><div id="summary-findings"></div><div id="summary-charts"></div><div id="selected-evidence" hidden></div></section><section id="plan-screen" hidden><h3 id="plan-title">실행 계획</h3><p id="plan-notice" class="muted"></p><div id="step-list"></div><div id="plan-changes"></div><details id="execution-history" class="execution-history"><summary>전문가 요청과 실제 실행 기록</summary><div class="node"><span class="node-label">EES 통합 Assistant</span><p id="assignment" class="muted"></p></div><div id="batches"></div><div id="join" class="line join" aria-hidden="true"></div><div class="node"><p id="synthesis" class="muted"></p><div id="comparisons"></div></div></details></section><section id="detail-section" class="detail" aria-labelledby="detail-title" hidden><h3 id="detail-title"></h3><p id="detail-status" class="muted"></p><nav class="detail-tabs" aria-label="단계 상세"><button id="detail-summary-tab" type="button">결과 요약</button><button id="detail-rationale-tab" type="button">판단 근거</button><button id="detail-data-tab" type="button">상세 자료</button></nav><div id="detail-summary" class="compact-summary"></div><div id="detail-rationale"></div><div id="detail-body" class="detail-data" hidden></div></section><p class="footnote">합성 시연 자료 · 실제 실행과 반환된 자료를 표시합니다.<br>새로고침하면 패널 기록은 초기화됩니다.</p></div></section>`;
      const q = id => shadow.getElementById(id);
      const divider = element('div'); divider.id = 'ees-cooperation-resizer'; divider.tabIndex = 0;
      divider.style.cssText = 'flex:0 0 10px;width:10px;cursor:col-resize;touch-action:none;display:flex;align-items:center;justify-content:center;z-index:31;';
      Object.entries({role: 'separator', 'aria-label': '대화와 협업 과정 너비 조절', 'aria-orientation': 'vertical', 'aria-controls': host.id}).forEach(([key, value]) => divider.setAttribute(key, value));
      // The separator is outside the panel shadow root. Keep keyboard focus on
      // its grip without drawing a full-height outline during pointer resizing.
      divider.append(element('style', '#ees-cooperation-resizer:focus{outline:none}#ees-cooperation-resizer:focus-visible:not([data-pointer-focus])>span{outline:2px solid var(--ees-blue,#6b91d5);outline-offset:3px}'));
      const grip = element('span'); grip.style.cssText = 'width:3px;height:36px;background:#8888;border-radius:2px;pointer-events:none;'; divider.append(grip);
      const slot = element('div'); slot.className = 'flex';
      const launcher = element('button', '업무 패널'); launcher.id = 'ees-work-panel-toggle'; launcher.type = 'button';
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
        launcher.setAttribute('aria-label', wantsOpen ? '업무 패널 닫기' : '업무 패널 열기');
        launcher.title = wantsOpen ? '업무 패널 닫기' : '업무 패널 열기';
        launcher.style.background = wantsOpen ? '#8882' : 'transparent';
      };
      const hide = () => {
        finishDrag(); resizeObserver.disconnect(); window.removeEventListener('resize', resize);
        host.remove(); divider.remove(); if (attached && !work) layout.column.style.minWidth = originalMinWidth;
      };
      const openRaw = (value = true, explicit = false, focusOnOpen = explicit) => {
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
      const open = (value = true, explicit = false, focusOnOpen = explicit) => {
        if (work) return value ? work.select(chatId, 'analysis', {open: true, focus: focusOnOpen}) : work.close(chatId);
        return openRaw(value, explicit, focusOnOpen);
      };
      const updateWorkTabs = () => {
        ['analysis', 'equipment', 'wo'].forEach(key => {
          const button = q('work-' + key); button.disabled = key !== 'analysis' && !work?.available(chatId, key);
          button.setAttribute('aria-selected', String((work?.selected(chatId) || 'analysis') === key));
          button.title = button.disabled ? '이 대화에서 해당 업무를 요청하면 사용할 수 있습니다.' : '';
        });
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
      const disclosure = (target, call, key, label) => {
        if (!disclosures.has(call.call_id)) disclosures.set(call.call_id, new Set());
        const openKeys = disclosures.get(call.call_id), details = element('details', undefined, 'disclosure'), summary = element('summary', label);
        details.open = openKeys.has(key); summary.dataset.focusKey = key;
        const record = {details, openKeys, key}; renderedDisclosures.push(record);
        details.addEventListener('toggle', () => {
          if (!renderedDisclosures.includes(record)) return;
          if (details.open) openKeys.add(key); else openKeys.delete(key);
        });
        details.append(summary); target.append(details); return details;
      };
      const renderComparison = (target, call) => {
        target.append(element('p', argumentsText(call.arguments), 'question detail-section'));
        const result = call.result;
        if (!result || result.ok !== true) { target.append(element('p', call.phase === 'failed' ? '비교를 완료하지 못했습니다.' : '아직 계산 결과를 받지 못했습니다.', 'muted detail-section')); return; }
        const calc = result.calculation || {};
        const summary = result.summary || {};
        const metrics = element('dl', undefined, 'metric-grid'); target.append(metrics);
        [['대상 사건', number(summary.total_events) + '건'], ['확인된 사건 평균', summary.mean_confirmed_minutes == null ? '계산 불가' : number(summary.mean_confirmed_minutes) + '분'], ['확인 / 미확인 / 판정 불가', [summary.confirmed_events, summary.not_confirmed_events, summary.unassessable_events].map(number).join(' / ') + '건'], ['평균 분모', number(summary.mean_denominator) + '건']].forEach(([label, value], index) => {
          const metric = element('div', undefined, 'metric'); metric.append(element('dt', label), element('dd', value, index === 2 ? 'small-value' : '')); metrics.append(metric);
        });
        (result.comparisons || []).forEach(comparison => {
          target.append(element('p', argumentsText(comparison.conditions), 'metric-title'));
          const rows = Object.entries(comparison.groups || {}).map(([key, group]) => [descriptions[key] || key, group.mean_confirmed_minutes == null ? '계산 불가' : number(group.mean_confirmed_minutes) + '분', number(group.mean_denominator), number(group.not_confirmed_events), number(group.unassessable_events)]);
          table(target, rows, ['구분', '평균', '분모', '미확인', '판정 불가']);
          target.append(element('p', '정비 후 재개 − 계획 기동: ' + (comparison.maintenance_minus_planned_minutes == null ? '계산 불가' : number(comparison.maintenance_minus_planned_minutes) + '분'), 'muted'));
        });
        const criteria = disclosure(target, call, 'criteria', '계산 기준과 자료 한계'), dl = element('dl'); criteria.append(dl);
        detailLine(dl, '판정 기준', [calc.conditions, calc.consecutive_samples == null ? null : calc.consecutive_samples + '개 연속 표본', calc.end].filter(Boolean).join(' · ') || '결과에 기준이 포함되지 않았습니다.');
        if (calc.mean_policy) detailLine(dl, '평균 계산', calc.mean_policy);
        if (calc.missing_policy) detailLine(dl, '누락 처리', calc.missing_policy);
        if (result.events?.length) {
          const details = disclosure(target, call, 'evidence', '사건별 근거 ' + result.events.length + '건');
          result.events.forEach(event => {
            const row = element('div', undefined, 'evidence'); row.append(element('p', [event.event_id, event.equipment_id, event.recipe_id].filter(Boolean).join(' · ')));
            row.append(element('p', '생산 재개: ' + text(event.resumed_at) + ' · ' + ({confirmed: '확인됨', not_confirmed_within_window: '관측 시간 내 미확인', unassessable: '자료 부족으로 판정 불가'}[event.state] || '상태 미확인'), 'muted'));
            row.append(element('p', '확인 소요: ' + (event.confirmed_after_minutes == null ? '계산 불가' : number(event.confirmed_after_minutes) + '분') + ' · 누락 표본: APC ' + number(event.missing_samples?.APC) + ', FDC ' + number(event.missing_samples?.FDC), 'muted'));
            row.append(element('p', '근거: ' + text(event.evidence_record_ids), 'muted')); details.append(row);
          });
        }
        if (result.message) target.append(element('p', result.message, 'notice'));
      };
      const shortText = (value, maximum = 180) => typeof value === 'string' ? value.trim().slice(0, maximum) + (value.trim().length > maximum ? '…' : '') : '';
      const summaryOf = call => {
        if (!call) return '아직 실행 결과를 받지 못했습니다.';
        if (call.kind === 'comparison' && call.result?.ok === true) {
          const summary = call.result.summary || {};
          return '대상 사건 ' + number(summary.total_events) + '건 · 확인된 사건 평균 ' + (summary.mean_confirmed_minutes == null ? '계산 불가' : number(summary.mean_confirmed_minutes) + '분') + ' · 평균 분모 ' + number(summary.mean_denominator) + '건';
        }
        if (call.analysis) return '전문가 회신 미리보기\n' + shortText(call.analysis);
        return ['failed', 'cancelled'].includes(call.phase) ? '결과를 확보하지 못했습니다. ' + statusText(call.phase) : '아직 실행 결과를 받지 못했습니다.';
      };
      const renderEvidence = () => {
        const target = q('selected-evidence'); target.replaceChildren(); target.hidden = !evidenceFilter;
        if (!evidenceFilter) return;
        const message = messages.get(selectedMessage), call = message?.calls.get(evidenceFilter.callId);
        if (!call?.result?.ok) { evidenceFilter = null; target.hidden = true; return; }
        target.className = 'evidence-selected';
        const rows = (call.result.events || []).filter(event => event.restart_type === evidenceFilter.group && Object.entries(evidenceFilter.conditions).every(([key, value]) => event[key] === value));
        target.append(element('h3', (descriptions[evidenceFilter.group] || evidenceFilter.group) + ' · 사건별 근거'), element('p', argumentsText(evidenceFilter.conditions), 'muted'));
        if (!rows.length) target.append(element('p', '이 구분에 해당하는 사건별 자료가 결과에 포함되지 않았습니다.', 'notice'));
        rows.forEach(event => {
          const row = element('div', undefined, 'evidence');
          row.append(element('p', [event.event_id, event.equipment_id, event.recipe_id].filter(Boolean).join(' · ')));
          row.append(element('p', '생산 재개: ' + text(event.resumed_at), 'muted'));
          row.append(element('p', '확인 소요: ' + (event.confirmed_after_minutes == null ? '계산 불가' : number(event.confirmed_after_minutes) + '분') + ' · ' + ({confirmed: '확인됨', not_confirmed_within_window: '관측 시간 내 미확인', unassessable: '자료 부족으로 판정 불가'}[event.state] || '상태 미확인')));
          row.append(element('p', '근거: ' + text(event.evidence_record_ids), 'muted')); target.append(row);
        });
        const close = element('button', '근거 접기'); close.type = 'button'; close.addEventListener('click', () => { evidenceFilter = null; renderEvidence(); }); target.append(close);
      };
      const renderChart = (target, call) => {
        if (call.result?.ok !== true) return;
        (call.result.comparisons || []).forEach((comparison, index) => {
          const chart = element('section', undefined, 'chart'), groups = Object.entries(comparison.groups || {});
          const values = groups.map(([, group]) => group.mean_confirmed_minutes).filter(value => typeof value === 'number' && Number.isFinite(value) && value >= 0);
          const maximum = Math.max(1, ...values);
          chart.append(element('h4', '안정화 확인까지의 평균 시간'), element('p', argumentsText(comparison.conditions), 'muted'));
          groups.forEach(([key, group]) => {
            const value = group.mean_confirmed_minutes, valid = typeof value === 'number' && Number.isFinite(value) && value >= 0;
            const bar = element('button', undefined, 'chart-bar'), track = element('span', undefined, 'bar-track'), fill = element('span', undefined, 'bar-fill');
            bar.type = 'button'; bar.dataset.group = key; bar.dataset.focusKey = 'chart-' + call.call_id + '-' + index + '-' + key;
            const valueText = valid ? number(value) + '분' : '계산 불가';
            bar.setAttribute('aria-label', (descriptions[key] || key) + ': ' + valueText + ', 평균 분모 ' + number(group.mean_denominator) + '건. 사건별 근거 보기');
            fill.style.width = (valid ? value / maximum * 100 : 0) + '%'; track.append(fill);
            bar.append(element('span', descriptions[key] || key), track, element('span', valueText));
            bar.addEventListener('click', () => {
              evidenceFilter = {callId: call.call_id, group: key, conditions: comparison.conditions || {}}; renderEvidence();
              const evidence = q('selected-evidence'); evidence.setAttribute('tabindex', '-1'); evidence.focus({preventScroll: true}); evidence.scrollIntoView?.({block: 'nearest'});
            });
            cardNodes.set(bar.dataset.focusKey, bar);
            chart.append(bar, element('p', '평균 분모 ' + number(group.mean_denominator) + '건 · 미확인 ' + number(group.not_confirmed_events) + '건 · 판정 불가 ' + number(group.unassessable_events) + '건', 'chart-meta'));
          });
          chart.append(element('p', '막대를 눌러 해당 사건과 근거를 확인하세요. 평균은 확인된 사건만 포함합니다.', 'chart-meta'));
          if (call.result.message) chart.append(element('p', call.result.message, 'notice'));
          target.append(chart);
        });
      };
      const renderWorkspace = (message, calls, plan) => {
        q('summary-screen').hidden = analysisScreen !== 'summary'; q('plan-screen').hidden = analysisScreen !== 'plan';
        q('view-summary').setAttribute('aria-selected', String(analysisScreen === 'summary')); q('view-plan').setAttribute('aria-selected', String(analysisScreen === 'plan'));
        q('summary-title').textContent = plan?.title || '분석 결과';
        q('summary-conclusion').textContent = plan?.conclusion || (plan?.stale ? '최신 진행 상태를 확인할 수 없습니다. 마지막으로 확보한 결과를 확인하세요.' : plan?.phase === 'planned' ? '실행 계획을 준비했습니다. 각 단계의 실행 상태를 확인하세요.' : plan?.phase === 'awaiting_summary' ? '확보한 결과와 한계를 정리하고 있습니다.' : plan?.phase === 'running' || calls.some(call => ['requested', 'analyzing', 'querying'].includes(call.phase)) ? '계획에 따라 자료를 확인하고 있습니다.' : '확보한 결과를 확인하세요. 최종 판단은 대화 답변에서도 확인할 수 있습니다.');
        q('summary-next').textContent = plan?.next_action ? '추천 행동 · ' + plan.next_action : ''; q('summary-next').hidden = !plan?.next_action;
        const failed = plan?.phase === 'partial' || plan?.stale || calls.some(call => ['failed', 'cancelled', 'partial'].includes(call.phase) || call.stale);
        const limits = [plan?.limitations, failed ? '일부 작업의 실패·부분 결과·상태 미확인이 있습니다. 단계별 한계를 확인하세요.' : ''].filter(Boolean).join(' ');
        q('summary-limits').textContent = limits; q('summary-limits').hidden = !limits;
        const findings = q('summary-findings'); findings.replaceChildren();
        (plan?.steps || []).filter(step => step.result_summary && step.type !== 'synthesis').slice(0, 3).forEach(step => {
          const button = element('button', undefined, 'finding'); button.type = 'button'; button.dataset.stepId = step.id;
          button.append(element('strong', step.title), element('p', shortText(step.result_summary), 'step-summary'));
          if (step.uncertainty) button.append(element('p', shortText(step.uncertainty, 100), 'notice'));
          button.addEventListener('click', () => chooseStep(step)); findings.append(button);
        });
        q('summary-charts').replaceChildren(); calls.filter(call => call.kind === 'comparison' && call.result?.ok === true).slice(-2).forEach(call => renderChart(q('summary-charts'), call)); renderEvidence();
        q('plan-title').textContent = plan?.title || '실행 계획';
        q('plan-notice').textContent = plan ? plan.stale ? '진행 알림이 중단되어 단계의 최신 상태를 확인할 수 없습니다.' : '단계를 선택하면 결과와 판단 근거를 확인할 수 있습니다.' : '이 분석에는 실행 전에 등록한 계획이 없습니다. 실제 실행 기록만 확인할 수 있습니다.';
        q('step-list').replaceChildren();
        (plan?.steps || []).forEach((step, index) => {
          const button = element('button', undefined, 'step'); button.type = 'button'; button.dataset.stepId = step.id; button.dataset.focusKey = 'step-' + step.id;
          button.setAttribute('aria-pressed', String(selectedStep === step.id));
          const body = element('span'); body.append(element('span', step.title, 'step-name'), element('p', step.system + (step.depends_on?.length ? ' · 앞 단계 결과 연결' : ''), 'step-meta'));
          const pill = element('span', plan.stale && ['pending', 'running'].includes(step.status) ? '상태 미확인' : step.type === 'synthesis' && step.status === 'completed' ? '정리됨' : statusText(step.status), 'pill'); pill.dataset.phase = step.status;
          button.append(element('span', index + 1, 'step-index'), body, pill); button.addEventListener('click', () => chooseStep(step)); q('step-list').append(button); cardNodes.set('step-' + step.id, button);
        });
        q('plan-changes').replaceChildren();
        (plan?.changes || []).forEach(change => q('plan-changes').append(element('p', typeof change === 'string' ? change : change.reason || '계획이 변경되었습니다.', 'notice')));
      };
      const chooseStep = step => {
        selectedStep = step.id; selectedCall = step.call_ids?.[0] || null; analysisScreen = 'plan'; detailTab = 'summary'; viewChosen = true; render();
      };
      const renderDetail = (call, step, plan) => {
        // Native toggle dispatch is queued. Capture live state before replacing
        // nodes so an arriving specialist event cannot undo a user's click.
        renderedDisclosures.forEach(({details, openKeys, key}) => { if (details.open) openKeys.add(key); else openKeys.delete(key); });
        renderedDisclosures = [];
        const target = q('detail-body'); target.replaceChildren();
        q('detail-section').hidden = analysisScreen !== 'plan' || (!step && !call);
        q('detail-summary').hidden = detailTab !== 'summary'; q('detail-rationale').hidden = detailTab !== 'rationale'; target.hidden = detailTab !== 'data';
        ['summary', 'rationale', 'data'].forEach(tab => q('detail-' + tab + '-tab').setAttribute('aria-selected', String(detailTab === tab)));
        q('detail-summary').textContent = step?.result_summary || summaryOf(call);
        if (step?.uncertainty) q('detail-summary').append(element('p', step.uncertainty, 'notice'));
        if (plan?.stale && step && ['pending', 'running'].includes(step.status)) q('detail-summary').append(element('p', '이 단계의 최신 진행 상태를 확인할 수 없습니다.', 'notice'));
        const rationale = q('detail-rationale'); rationale.replaceChildren();
        [['실행 전 · 이 단계를 선택한 이유', step?.reason_before || '실행 전에 기록된 선택 이유가 없습니다.'], ['실행 후 · 확보한 근거에 대한 판단', step?.judgment_after || '아직 실행 후 판단이 기록되지 않았습니다.'], ['남은 한계', step?.uncertainty || '별도로 기록된 한계가 없습니다. 결과의 자료 범위를 함께 확인하세요.']].forEach(([label, value]) => {
          const section = element('section', undefined, 'rationale-block'); section.append(element('h4', label), element('p', value)); rationale.append(section);
        });
        rationale.append(element('p', '실행 전에 기록한 선택 이유와 실행 후 공개 판단 요약입니다. 모델 내부 사고의 재현은 아닙니다.', 'footnote'));
        if (step) {
          q('detail-title').textContent = step.title; q('detail-status').textContent = step.system + ' · ' + (plan?.stale && ['pending', 'running'].includes(step.status) ? '최신 상태 미확인 · 마지막 확인: ' + statusText(step.status) : statusText(step.status));
          if (step.call_ids?.length > 1) {
            const links = element('div', undefined, 'view-tabs');
            step.call_ids.forEach((id, index) => { const button = element('button', '실행 ' + (index + 1)); button.type = 'button'; button.setAttribute('aria-selected', String(selectedCall === id)); button.addEventListener('click', () => { selectedCall = id; render(); }); links.append(button); }); target.append(links);
          }
        }
        if (!call) { if (!step) { q('detail-title').textContent = '작업 상세'; q('detail-status').textContent = '확인할 작업을 선택하세요.'; } target.append(element('p', '연결된 실행 자료가 아직 없습니다.', 'muted')); return; }
        if (!step) q('detail-title').textContent = call.kind === 'specialist' ? call.system + ' Assistant' : 'EES · 교차 비교';
        if (!step) q('detail-status').textContent = call.stale ? '최신 진행 상태 미확인 · 마지막 확인: ' + statusText(call.phase) : call.kind === 'comparison' && call.phase === 'completed' ? '비교 완료' : statusText(call.phase);
        if (call.phase === 'partial') target.append(element('p', '일부 회신 또는 근거만 확보했습니다. 한계를 함께 확인하세요.', 'notice'));
        if (call.phase === 'failed' || call.phase === 'cancelled') target.append(element('p', call.phase === 'cancelled' ? '이 작업은 취소되었습니다. 다른 작업의 결과는 유지됩니다.' : '이 작업을 완료하지 못했습니다. 다른 작업의 결과는 유지됩니다.', 'notice'));
        if (call.kind === 'comparison') renderComparison(target, call);
        else {
          const question = call.request?.question || '요청 내용이 전달되지 않았습니다.', questionLabel = call.request?.kind === 'followup' ? '보완 요청' : '맡긴 질문';
          if (question.length > 180 || question.split('\n').length > 3) disclosure(target, call, 'question', questionLabel + ' 전체 보기').append(element('p', question, 'plain question'));
          else { const section = element('section', undefined, 'detail-section'); section.append(element('p', questionLabel, 'section-label'), element('p', question, 'plain question')); target.append(section); }
          const analysis = typeof call.analysis === 'string' ? call.analysis : '', isExpanded = expanded.has(call.call_id), preview = analysis.length > 700 && !isExpanded;
          const replySection = element('section', undefined, 'detail-section'), reply = element('div', undefined, 'reply' + (preview ? ' truncate' : ''));
          replySection.append(element('p', '전문가 회신', 'section-label')); target.append(replySection);
          if (call.analysis_truncated) replySection.append(element('p', '회신이 길어 끝부분 16,000자만 전달되었습니다. 전체 회신으로 간주하지 마세요.', 'notice'));
          if (preview) replySection.append(element('p', '전달된 회신 앞부분 · 전체 보기로 이어서 확인', 'preview-label'));
          if (analysis) readable(reply, analysis);
          else reply.append(element('p', ['completed', 'partial'].includes(call.phase) ? '표시할 회신이 없습니다.' : '아직 회신을 받지 못했습니다.', 'muted'));
          replySection.append(reply);
          if (analysis.length > 700) {
            const button = element('button', isExpanded ? '회신 접기' : '회신 전체 보기', 'expand'); button.type = 'button'; button.dataset.focusKey = 'expand'; button.setAttribute('aria-expanded', String(isExpanded));
            button.addEventListener('click', () => { if (expanded.has(call.call_id)) expanded.delete(call.call_id); else expanded.add(call.call_id); render(); }); replySection.append(button);
          }
          const queries = disclosure(target, call, 'queries', '조회 근거 · ' + (call.queries?.length ? call.queries.length + '회 요청' : '기록 없음'));
          if (!call.queries?.length) queries.append(element('p', call.phase === 'requested' ? '아직 자료 조회를 시작하지 않았습니다.' : '기록된 자료 조회가 없습니다.', 'muted'));
          (call.queries || []).forEach(query => {
            const card = element('div', undefined, 'query');
            card.append(element('p', '조회 ' + number(query.index) + ' · ' + ({querying: '조회 중', completed: '조회 완료', failed: '조회 실패', cancelled: '조회 취소'}[query.status] || '상태 미확인')));
            card.append(element('p', argumentsText(query.arguments), 'muted'));
            if (query.record_count != null) card.append(element('p', '조회 결과 ' + number(query.record_count) + '건', 'muted'));
            if (query.event_ids?.length) card.append(element('p', '사건: ' + query.event_ids.join(', '), 'muted'));
            queries.append(card);
          });
        }
      };
      const render = () => {
        const message = messages.get(selectedMessage); if (!message) return;
        const focusKey = shadow.activeElement?.dataset?.focusKey, scrollTop = q('scroll').scrollTop;
        cardNodes.clear();
        const all = Array.from(message.calls.values()), plan = all.filter(call => call.kind === 'plan').at(-1);
        const calls = all.filter(call => call.kind !== 'plan'), specialists = calls.filter(call => call.kind === 'specialist'), comparisons = calls.filter(call => call.kind === 'comparison');
        if (selectedStep && !plan?.steps.some(step => step.id === selectedStep)) selectedStep = null;
        if (!selectedStep && selectedCall === null && plan?.steps?.length) selectedStep = plan.steps.find(step => step.status === 'running')?.id || plan.steps[0].id;
        const step = plan?.steps.find(step => step.id === selectedStep);
        if (step && !step.call_ids?.includes(selectedCall)) selectedCall = step.call_ids?.[0] || null;
        if (!step && !message.calls.has(selectedCall)) selectedCall = calls[0]?.call_id || null;
        const done = specialists.filter(call => call.phase === 'completed').length, pending = specialists.filter(call => !call.stale && ['requested', 'analyzing', 'querying'].includes(call.phase)).length;
        const status = all.some(call => call.stale) ? '대화 이동 중 진행 알림이 중단되어 최신 상태를 확인할 수 없습니다.' : plan ? plan.phase === 'completed' ? '분석 정리됨 · 단계와 근거를 확인하세요.' : statusText(plan.phase) : pending ? '전문 분석 ' + pending + '건 진행 중 · 회신 완료 ' + done + '건' : specialists.length ? '전문 분석 종료 · 회신 완료 ' + done + '건 · 작업별 상태를 확인하세요.' : 'EES의 교차 비교를 표시합니다.';
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
            card.append(element('span', call.request?.kind === 'followup' ? '보완 분석' : call.queries?.length ? '조회 요청 ' + call.queries.length + '회' : '전문 분석', 'muted'));
            card.addEventListener('click', () => { selectedCall = call.call_id; selectedStep = call.step_id || null; analysisScreen = 'plan'; detailTab = 'data'; viewChosen = true; render(); }); cards.append(card); cardNodes.set(call.call_id, card);
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
          button.append(element('p', argumentsText(call.arguments), 'muted')); button.addEventListener('click', () => { selectedCall = call.call_id; selectedStep = call.step_id || null; analysisScreen = 'plan'; detailTab = 'data'; viewChosen = true; render(); }); q('comparisons').append(button); cardNodes.set(call.call_id, button);
        });
        const select = q('message-select'); select.replaceChildren(); q('history').hidden = messages.size < 2;
        let index = 0; messages.forEach((item, id) => { index += 1; const first = Array.from(item.calls.values())[0]; const label = first?.title || first?.request?.question || '교차 비교'; const option = element('option', '분석 ' + index + (id === latestMessage ? ' · 최근' : '') + ' — ' + label.slice(0, 42)); option.value = id; select.append(option); }); select.value = selectedMessage;
        renderWorkspace(message, calls, plan); renderDetail(message.calls.get(selectedCall), step, plan); q('scroll').scrollTop = scrollTop;
        if (focusKey) { const node = cardNodes.get(focusKey) || (['expand', 'question', 'queries', 'criteria', 'evidence'].includes(focusKey) ? q('detail-body').querySelector('[data-focus-key="' + focusKey + '"]') : null); node?.focus({preventScroll: true}); }
      };
      const receive = event => {
        let message = messages.get(event.message_id);
        if (!message) {
          message = {calls: new Map()}; messages.set(event.message_id, message);
          const candidate = document.getElementById('message-' + event.message_id), previous = document.getElementById('message-' + latestMessage);
          const appearsOlder = candidate && previous && Boolean(candidate.compareDocumentPosition(previous) & 4);
          if (!latestMessage || (['requested', 'planned'].includes(event.phase) && !appearsOlder)) {
            const firstMessage = !latestMessage;
            latestMessage = event.message_id; selectedMessage = event.message_id; selectedCall = null; selectedStep = null; evidenceFilter = null; detailTab = 'summary';
            analysisScreen = event.kind === 'plan' && ['planned', 'running', 'awaiting_summary'].includes(event.phase) ? 'plan' : 'summary'; viewChosen = false;
            autoOpenRequested = (firstMessage || ['requested', 'planned'].includes(event.phase)) && !appearsOlder && location.pathname === route(chatId);
          }
        }
        const old = message.calls.get(event.call_id);
        if (old && (old.seq >= event.seq || old.kind !== event.kind || old.system !== event.system || old.batch_id !== event.batch_id)) return false;
        message.calls.set(event.call_id, {...event, stale: false});
        if (event.kind === 'plan' && ['completed', 'partial'].includes(event.phase) && selectedMessage === event.message_id && !viewChosen) analysisScreen = 'summary';
        render();
        return true;
      };
      const detach = () => {
        if (location.pathname !== route(chatId)) {
          messages.forEach(message => message.calls.forEach(call => { if (['planned', 'running', 'awaiting_summary', 'requested', 'analyzing', 'querying'].includes(call.phase)) call.stale = true; }));
          render();
        }
        hide(); slot.remove(); attached = false; layout = null;
      };
      const attach = nextLayout => {
        layout = nextLayout; originalMinWidth = layout.column.style.minWidth; attached = true;
        if (work) {
          work.register(chatId, {key: 'analysis', label: '분석 과정', hostId: host.id, open: () => openRaw(true, true, false), close: () => openRaw(false), isOpen: () => host.isConnected, onChange: updateWorkTabs, focus: () => (divider.hidden ? q('close') : q('work-analysis')).focus({preventScroll: true})});
          work.restore(chatId); work.sync();
        } else { layout.toolbar.insertBefore(slot, layout.wrapper || null); launcherState(); if (wantsOpen) open(); }
        theme(); updateWorkTabs();
      };
      const alive = () => attached && location.pathname === route(chatId) && layout.row.isConnected && document.querySelector('#chat-container #chat-pane') === layout.anchor && layout.anchor.parentElement === layout.column && layout.column.parentElement === layout.row && (work || (slot.parentElement === layout.toolbar && launcher.isConnected));
      divider.addEventListener('pointerdown', event => {
        if (divider.hidden || event.button !== 0 || event.isPrimary === false) return;
        finishDrag(); drag = {id: event.pointerId, x: event.clientX, width: panelWidth, selection: document.body.style.userSelect, cursor: document.body.style.cursor};
        document.body.style.userSelect = 'none'; document.body.style.cursor = 'col-resize';
        try { divider.setPointerCapture(event.pointerId); } catch (_) { finishDrag(); return; }
        // Programmatic focus can retain :focus-visible after keyboard input.
        divider.dataset.pointerFocus = 'true';
        divider.focus({preventScroll: true}); event.preventDefault();
      });
      divider.addEventListener('pointermove', event => { if (drag && drag.id === event.pointerId) setWidth(drag.width + drag.x - event.clientX); });
      ['pointerup', 'pointercancel', 'lostpointercapture'].forEach(type => divider.addEventListener(type, finishDrag));
      divider.addEventListener('keydown', event => {
        delete divider.dataset.pointerFocus;
        if (divider.hidden || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
        event.preventDefault(); setWidth(event.key === 'Home' ? 350 : event.key === 'End' ? maximumWidth : panelWidth + (event.key === 'ArrowLeft' ? 20 : -20));
      });
      divider.addEventListener('blur', () => { delete divider.dataset.pointerFocus; });
      q('close').addEventListener('click', () => { open(false); if (work) work.focus(chatId); else launcher.focus({preventScroll: true}); });
      launcher.addEventListener('click', () => open(!wantsOpen, true));
      shadow.addEventListener('keydown', event => { if (event.key === 'Escape') { open(false); if (work) work.focus(chatId); else launcher.focus({preventScroll: true}); } });
      ['analysis', 'equipment', 'wo'].forEach(key => q('work-' + key).addEventListener('click', () => { if (work?.available(chatId, key)) work.select(chatId, key, {open: true}); }));
      ['summary', 'plan'].forEach(screen => q('view-' + screen).addEventListener('click', () => { analysisScreen = screen; viewChosen = true; render(); }));
      ['summary', 'rationale', 'data'].forEach(tab => q('detail-' + tab + '-tab').addEventListener('click', () => { detailTab = tab; viewChosen = true; render(); }));
      q('message-select').addEventListener('change', () => { if (messages.has(q('message-select').value)) { selectedMessage = q('message-select').value; selectedCall = null; selectedStep = null; evidenceFilter = null; render(); } });
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
