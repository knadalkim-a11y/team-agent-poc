// Browser check of design mock 23, revision 3 (tool job list): walks the flow on both sides and checks what shows.
// usage: node check_mock.js MOCK.html REPORT.json [SHOTDIR]
const { chromium } = require('playwright');
const fs = require('fs'); const path = require('path');
const [file, reportPath, shotDir] = process.argv.slice(2);
const results = []; let current = '';
const check = (name, ok, detail) => { results.push({ size: current, name, ok: !!ok, detail: detail === undefined ? '' : String(detail) }); };
const lum = c => { const m = c.match(/[\d.]+/g).map(Number); const f = v => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }; return .2126 * f(m[0]) + .7152 * f(m[1]) + .0722 * f(m[2]); };
const contrast = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05); };
const META = '도구 사용 · 담당자 확인', EARLIER = '앞 작업 ‘기준 문서 확인’ 결과 사용', LATER = '뒤 작업 ‘하위 문서 목록 조회’ 결과 사용', GONE = '결과를 받던 작업이 없어짐';
const MENU = '업무 절차 정보·분류 수정|다른 이름으로 저장|내용 확인|게시 내림';

async function run(browser, width, height) {
  current = width + 'x' + height;
  const page = await browser.newPage({ viewport: { width, height } });
  const errors = []; page.on('pageerror', e => errors.push(String(e))); page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  await page.goto('file://' + path.resolve(file)); await page.evaluate(() => document.fonts.ready);
  const now = '.mk-pane[data-side=now] ', after = '.mk-pane[data-side=after] ';
  const show = async (scene, view, form, card) => { await page.evaluate(([s, v, f, c]) => window.mockShow(s, v, f, c), [scene, view || 'side', form || 'fold', card || 'open']); await page.waitForTimeout(120); };
  const strip = () => page.locator('#mock-step-text').textContent();
  // a closed <details> keeps its content's boxes (content-visibility), so ask the browser whether it is rendered
  const shown = sel => page.evaluate(s => { const e = document.querySelector(s); if (!e) return false; const c = getComputedStyle(e), r = e.getBoundingClientRect(); return c.display !== 'none' && c.visibility !== 'hidden' && r.width > 1 && r.height > 1 && e.checkVisibility(); }, sel);
  const text = sel => page.evaluate(s => { const e = document.querySelector(s); return e ? e.textContent.trim() : null; }, sel);
  const count = sel => page.locator(sel).count();
  const state = () => page.evaluate(() => window.mockState());
  const badge = async () => (await text('#mock-badge')).split(' · ').pop();
  const noteText = () => page.evaluate(() => document.querySelector('#mock-note').textContent);
  const focused = () => page.evaluate(() => { const e = document.activeElement; return e ? [(e.closest('.mk-pane') || { getAttribute: () => '' }).getAttribute('data-side'), e.getAttribute('data-author-action') || e.getAttribute('name') || e.tagName, e.getAttribute('data-id') || ''].join('/') : ''; });
  const shot = async name => { if (shotDir) { await page.waitForTimeout(3300); await page.screenshot({ path: path.join(shotDir, `${name}-${width}.png`) }); } };
  const own = 'e => [...e.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join("").trim()';
  const rows = side => page.evaluate(([s, ownText]) => { const mine = eval(ownText); return [...document.querySelectorAll(s + '.ew-job-row')].map(r => { const name = r.querySelector('.ew-job-row-label>span'), tag = name.querySelector('.ew-author-tag'), meta = r.querySelector('.ew-job-meta'), from = r.querySelector('.ew-job-from'); return { id: r.getAttribute('data-job-id'), h: Math.round(r.getBoundingClientRect().height), name: mine(name), chip: tag ? tag.textContent.trim() : '', meta: meta ? mine(meta) : '', from: from ? from.textContent.trim() : '', said: meta ? meta.textContent : '', lines: r.innerText.split('\n').map(x => x.trim()).filter(Boolean).length, binding: !!r.querySelector('[data-api-job-binding]'), bound: (r.querySelector('[data-api-job-binding]') || { textContent: '' }).textContent, action: (r.querySelector('.ew-api-row-action') || { textContent: '' }).textContent.trim(), actionName: (r.querySelector('.ew-api-row-action') || { getAttribute: () => '' }).getAttribute('aria-label') || '' }; }); }, [side, own]);
  // how far a mark stands from the end of the text before it, on the same line
  const markGap = sel => page.evaluate(s => { const tag = document.querySelector(s), range = document.createRange(), node = [...tag.parentElement.childNodes].find(n => n.nodeType === 3); range.selectNodeContents(node); const rects = [...range.getClientRects()], last = rects[rects.length - 1], b = tag.getBoundingClientRect(); return { gap: Math.round(b.left - last.right), sameLine: b.top < last.bottom && b.bottom > last.top, left: Math.round(b.left - rects[0].left) }; }, sel);
  const overview = side => page.evaluate(s => document.querySelector(s + '#ees-work-designer').getAttribute('data-api-overview'), side);
  const listTop = side => page.evaluate(s => Math.round(document.querySelector(s + '.ew-stage-list').getBoundingClientRect().top - document.querySelector(s + '#ees-work-panel').getBoundingClientRect().top), side);
  const inView = side => page.evaluate(s => { const sc = document.querySelector(s + '.ew-author-scroll').getBoundingClientRect(); return [...document.querySelectorAll(s + '.ew-job-row')].map(r => { const b = r.getBoundingClientRect(); return b.top >= sc.top - 1 && b.bottom <= sc.bottom + 1; }); }, side);
  const fields = side => shown(side + 'input[name=overview_name]');

  check('the mock opens with today\'s screen and the proposal side by side', (await state()).view === 'now+after' && (await count('.mk-pane')) === 2, (await state()).view);
  check('nothing of the view-first proposal is left in this revision', (await count('.ew-view-edit')) === 0 && (await count('[data-side=view]')) === 0 && (await count('[data-mark-pick]')) === 0);
  check('the strip offers the two things left to choose', (await count('[data-form-pick]')) === 2 && (await count('[data-card-pick]')) === 2 && (await state()).form === 'fold' && (await state()).card === 'open');
  check('a short window starts with the explanation folded, a tall one open', (await page.evaluate(() => document.querySelector('#mock-guide').getAttribute('data-collapsed'))) === String(height < 900));
  if (height < 900) {
    check('folded: the screens and the two switches are still there to press', (await shown('[data-step=T4]')) && (await shown('[data-form-pick=now]')) && (await shown('[data-card-pick=fold]')) && !(await shown('#mock-step-text')));
    const line = await page.evaluate(() => { const a = document.querySelector('#mock-badge').getBoundingClientRect(), b = document.querySelector('#mock-fold').getBoundingClientRect(); return Math.round(Math.abs((a.top + a.bottom) / 2 - (b.top + b.bottom) / 2)); });
    check('folded: the strip is one line, so the screens below keep their height', line <= 2, line);
    await page.click('[data-form-pick=now]'); await page.waitForTimeout(120);
    check('folded: the fields switch works without opening the explanation', await fields(after));
    await page.click('[data-form-pick=fold]'); await page.waitForTimeout(120);
    await page.click('#mock-fold');
  }
  if (width >= 1366) {
    const open = await page.evaluate(() => { const a = document.querySelector('#mock-badge').getBoundingClientRect(), b = document.querySelector('#mock-fold').getBoundingClientRect(); return Math.round(Math.abs((a.top + a.bottom) / 2 - (b.top + b.bottom) / 2)); });
    check('opened: the buttons of the strip are still one line', open <= 2, open);
  }

  // ---- T1: the procedure as it opens
  await show('T1');
  check('T1 badge says it is a mock and names the screen', (await text('#mock-badge')) === '시안 3 · 저장·실행 안 됨 · T1');
  check('T1 now: the summary hides 단계 추가', (await overview(now)) === 'true' && !(await shown(now + '[data-author-action=add_stage]')));
  check('T1 now: the way in is ⋯ → 절차 편집', (await text(now + '[data-author-action=api_structure_edit]')) === '절차 편집');
  check('T1 after: 단계 추가 and 시작할 때 물어볼 것 show as the procedure opens', (await shown(after + '[data-author-action=add_stage]')) && (await shown(after + '[data-author-action=start_input_add]')));
  check('T1 after: no 절차 편집 / 도구 연결 보기 in the menu', (await count(after + '[data-author-action=api_structure_edit]')) === 0);
  check('T1 after: the other menu items stay', (await page.locator(after + '.ew-procedure-menu button').allTextContents()).join('|') === MENU);
  check('T1 after: the name, category and purpose fields are folded', !(await fields(after)) && !(await shown(after + '.ew-procedure-brief-close')));
  const brief = await page.evaluate(s => { const p = document.querySelector(s + '.ew-procedure-brief'), b = p.querySelector('button'), r = p.getBoundingClientRect(), c = getComputedStyle(b); return { parts: [...p.querySelectorAll(':scope>span')].map(e => [...e.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join('')), read: [...p.querySelectorAll(':scope>span')].map(e => e.textContent).join(' / '), w: Math.round(r.width), link: b.textContent, inMenu: !!b.closest('details,.ew-procedure-menu,[role=menu]'), expanded: b.getAttribute('aria-expanded'), h: Math.round(r.height), linkH: Math.round(b.getBoundingClientRect().height), color: c.color, tabs: Math.round(r.top - document.querySelector(s + '.ew-author-tabs, ' + s + '.ew-tabs').getBoundingClientRect().bottom) }; }, after);
  check('T1 after: one line says the category and the purpose', brief.parts.join('|') === '운영|업무 목적 없음' && brief.h <= 36 && brief.w <= 536, JSON.stringify(brief));
  check('T1 after: a screen reader hears which is the category', brief.read === '업무 분류 운영 / 업무 목적 없음', brief.read);
  check('T1 after: 절차 정보 수정 is a link on that line, under the tabs, not a menu item', brief.link === '절차 정보 수정' && !brief.inMenu && brief.expanded === 'false' && brief.linkH >= 28 && brief.tabs >= 0 && brief.tabs <= 48, JSON.stringify(brief));
  check('T1 after: the link is readable on the panel', contrast(brief.color, 'rgb(255,255,255)') >= 4.5, contrast(brief.color, 'rgb(255,255,255)').toFixed(2));
  const tops = { now: await listTop(now), fold: await listTop(after) };
  await shot('T1-side');
  // a purpose as long as a real one: the line cuts it with an ellipsis and its link stays in view
  const LONG = '매주 월요일 오전에 설비 세 곳의 상태를 확인하고 이상이 있으면 담당자에게 알린 뒤 조치 결과까지 기록해 다음 주 점검에서 다시 확인할 수 있게 합니다.';
  for (const one of [false, true]) {
    await show('T1', one ? 'after' : 'side');
    const long = await page.evaluate(([s, text]) => { const p = document.querySelector(s + '.ew-procedure-brief'), span = p.querySelector(':scope>span+span'), link = p.querySelector('button'), sc = document.querySelector(s + '.ew-author-scroll'); span.lastChild.textContent = text; span.setAttribute('data-empty', 'false'); const l = link.getBoundingClientRect(), b = sc.getBoundingClientRect(); return { cut: span.scrollWidth > span.clientWidth + 1, line: Math.round(p.getBoundingClientRect().height), w: Math.round(p.getBoundingClientRect().width), linkIn: l.right <= b.right - 8 && l.left >= b.left, sideways: sc.scrollWidth - sc.clientWidth, panel: document.documentElement.scrollWidth - innerWidth }; }, [after, LONG]);
    check(`T1 after (${one ? 'one side' : 'side by side'}): a long purpose is cut with an ellipsis on one line, the link stays in view, nothing scrolls sideways`, long.cut && long.line <= 36 && long.w <= 536 && long.linkIn && long.sideways <= 0 && long.panel <= 0, JSON.stringify(long));
    if (!one) await shot('T1-side-long-purpose');
  }
  await show('T1');
  await page.click(after + '.ew-procedure-brief [data-author-action=info_toggle]'); await page.waitForTimeout(120);
  tops.open = await listTop(after);
  check('T1 after: 절차 정보 수정 opens the three fields in place, on that side only', (await fields(after)) && (await shown(after + 'select[name=overview_category], ' + after + '#ew-procedure-info select')) && (await shown(after + 'textarea[name=overview_description]')) && !(await shown(after + '.ew-procedure-brief')) && !(await fields(now)) && (await badge()) === 'T1');
  check('T1 after: the keyboard lands in the first field', (await focused()) === 'after/overview_name/', await focused());
  check('T1 after: 접기 under the fields folds them again', (await text(after + '.ew-procedure-brief-close')) === '접기' && (await shown(after + '.ew-procedure-brief-close')) && (await page.getAttribute(after + '.ew-procedure-brief-close', 'aria-label')) === '절차 정보 접기');
  const closePlace = await page.evaluate(s => { const b = document.querySelector(s + '.ew-procedure-brief-close'), range = document.createRange(); range.selectNodeContents(b); const label = document.querySelector(s + '#ew-procedure-info label'), lr = document.createRange(); lr.selectNodeContents([...label.childNodes].find(n => n.nodeType === 3) || label); const area = document.querySelector(s + 'textarea[name=overview_description]').getBoundingClientRect(); return { text: Math.round(range.getBoundingClientRect().left), label: Math.round(lr.getBoundingClientRect().left), below: Math.round(b.getBoundingClientRect().top - area.bottom) }; }, after);
  check('T1 after: 접기 starts on the fields\' label edge, clear of the purpose box', Math.abs(closePlace.text - closePlace.label) <= 1 && closePlace.below >= 6, JSON.stringify(closePlace));
  check('T1 after: opening the fields pushes the stage list down', tops.open > tops.fold + 80, JSON.stringify(tops));
  await shot('T1-side-info-open');
  await page.fill(after + 'textarea[name=overview_description]', '문서 구조를 확인합니다.');
  await page.click(after + '.ew-procedure-brief-close'); await page.waitForTimeout(120);
  check('T1 after: folding after typing says what the product does with it', (await noteText()).includes('초안에 남고'), await noteText());
  check('T1 after: folded again, the keyboard is back on the link', !(await fields(after)) && (await focused()) === 'after/info_toggle/', await focused());
  await page.keyboard.press('Shift+Tab'); await page.keyboard.press('Tab');
  const linkRing = await page.evaluate(s => { const c = getComputedStyle(document.querySelector(s)); return c.outlineStyle + ' ' + c.outlineWidth; }, after + '.ew-procedure-brief [data-author-action=info_toggle]');
  check('T1 after: the link shows a focus ring from the keyboard', /solid 2px/.test(linkRing), linkRing);
  check('T1: with the fields folded the stage list starts within 140px of where the summary has it', tops.fold - tops.now <= 140 && tops.fold - tops.now >= 0, JSON.stringify(tops));
  await page.click('[data-form-pick=now]'); await page.waitForTimeout(120);
  tops.asNow = await listTop(after);
  check('T1 option 지금처럼: the fields are open and there is nothing to fold them with', (await fields(after)) && !(await shown(after + '.ew-procedure-brief')) && !(await shown(after + '.ew-procedure-brief-close')) && tops.asNow > tops.fold + 80, JSON.stringify(tops));
  check('T1 option: the now side does not change', !(await fields(now)) && (await listTop(now)) === tops.now);
  check('T1 option 지금처럼: the explanation says the fields stay open, not that they are folded', (await strip()).includes('늘 펼쳐져') && !(await strip()).includes('접혀'), await strip());
  await shot('T1-side-fields-open');
  await page.click('[data-form-pick=fold]'); await page.waitForTimeout(120);
  check('T1 option 접기: folded again, and the explanation says so', !(await fields(after)) && (await shown(after + '.ew-procedure-brief')) && (await strip()).includes('한 줄로 접혀'));

  // ---- T2: a stage open
  await show('T2');
  const nowRows = await rows(now), afterRows = await rows(after);
  check('T2 now: each job shows its name and three more lines', nowRows.length === 2 && nowRows.every(r => r.binding && r.lines >= 4), JSON.stringify(nowRows.map(r => r.lines)));
  check('T2 after: each job is its name and one line, nothing under it', afterRows.length === 2 && afterRows.every(r => !r.binding && !r.action && !r.chip && r.lines <= 3), JSON.stringify(afterRows));
  check('T2 after: the line is the one the product writes today', afterRows[0].meta === META && afterRows[0].from === '' && afterRows[1].meta === META, afterRows[0].meta);
  check('T2 after: the job that takes an earlier job\'s result says so, and calls it an earlier job', afterRows[1].from === EARLIER, afterRows[1].from);
  check('T2 after: read aloud or copied, the two parts of the line do not run together', afterRows[1].said === META + ' ' + EARLIER, afterRows[1].said);
  const mark = await page.evaluate(s => { const e = document.querySelector(s + '.ew-job-from'), c = getComputedStyle(e), m = getComputedStyle(e.parentElement), r = e.getBoundingClientRect(), p = e.parentElement.getBoundingClientRect(); return { line: c.borderLeftWidth + ' ' + c.borderLeftStyle, pad: c.paddingLeft, color: c.color, meta: m.color, sameLine: Math.abs(r.top - p.top) <= 2 && r.bottom <= p.bottom + 1 }; }, after);
  check('T2 after: that part is set apart by a line and a darker tone, on the same line', mark.line === '1px solid' && mark.pad === '10px' && mark.color !== mark.meta && contrast(mark.color, 'rgb(255,255,255)') > contrast(mark.meta, 'rgb(255,255,255)') && mark.sameLine, JSON.stringify(mark));
  check('T2 after: a job row is at most 64px tall', afterRows.every(r => r.h <= 64), JSON.stringify(afterRows.map(r => r.h)));
  check('T2 after: rows are shorter than now', afterRows.reduce((a, r) => a + r.h, 0) < nowRows.reduce((a, r) => a + r.h, 0), afterRows.reduce((a, r) => a + r.h, 0) + ' < ' + nowRows.reduce((a, r) => a + r.h, 0));
  check('T2 after: 작업 추가 and 단계 추가 show', (await shown(after + '[data-author-action=add_job]')) && (await shown(after + '[data-author-action=add_stage]')));
  check('T2 now: 작업 추가 and 단계 추가 are hidden in the summary', !(await shown(now + '[data-author-action=add_job]')) && !(await shown(now + '[data-author-action=add_stage]')));
  check('T2: the jobs are in view on both sides without scrolling by hand', (await inView(now)).every(Boolean) && (await inView(after)).every(Boolean), JSON.stringify([await inView(now), await inView(after)]));
  await shot('T2-side');
  // now side: ⋯ → 절차 편집 shows today's edit view with the note boxes
  await page.click(now + '.ew-procedure-menu>summary'); await page.waitForTimeout(100);
  await page.click(now + '[data-author-action=api_structure_edit]'); await page.waitForTimeout(120);
  check('T2 now: after 절차 편집 the edit view shows, with the fields open and the note under each job', (await overview(now)) === 'false' && (await shown(now + '[data-author-action=add_stage]')) && (await fields(now)) && (await count(now + '.ew-job-row>.ew-api-job-binding')) === 2);
  check('T2 now: the edit view writes the same line the after side keeps', (await rows(now))[0].meta === META);
  check('T2 now: the caption says which of the two views this is', (await text(now.trim() + '>.mk-pane-label small')) === '⋯ → 절차 편집을 누른 뒤');
  await shot('T2-side-now-edit');
  await show('T2');

  // ---- the flow: list → procedure → stage → job → details → back
  await page.click(after + '[data-author-action=list]'); await page.waitForTimeout(120);
  check('flow: back to the list on both sides, numbered T0', (await state()).screen === 'list' && (await badge()) === 'T0' && (await shown(now + '[data-author-action=create]')) && (await shown(after + '[data-author-action=create]')));
  await page.evaluate(sel => { const e = [...document.querySelectorAll(sel + '[data-author-action=open]')].find(x => !x.textContent.includes('Confluence')); e && e.click(); }, after); await page.waitForTimeout(120);
  check('flow: the other procedure (people and a tool) opens in the edit view on both sides', (await state()).mixed && (await badge()) === 'T5' && (await shown(now + '[data-author-action=add_stage]')) && (await shown(after + '[data-author-action=add_stage]')) && (await text('h2')) === '주간 설비 점검');
  await page.click(after + '[data-author-action=list]'); await page.waitForTimeout(120);
  await page.evaluate(sel => { const e = [...document.querySelectorAll(sel + '[data-author-action=open]')].find(x => x.textContent.includes('Confluence')); e && e.click(); }, after); await page.waitForTimeout(120);
  check('flow: the guide opens — summary now, edit view after, its fields folded', (await badge()) === 'T1' && (await overview(now)) === 'true' && (await shown(after + '[data-author-action=add_stage]')) && !(await fields(after)));
  await page.click(after + '[data-author-action=stage_toggle]'); await page.waitForTimeout(120);
  check('flow: opening the stage on one side opens it on the other, and the badge follows', (await badge()) === 'T2' && (await count(now + '.ew-job-row')) === 2 && (await count(after + '.ew-job-row')) === 2);
  check('flow: the keyboard stays on the stage row that was pressed', (await focused()) === 'after/stage_toggle/documents', await focused());
  await page.click(after + '[data-author-action=node][data-id=page]'); await page.waitForTimeout(120);
  let st = await state();
  check('flow: a job row opens the job page on both sides', st.screen === 'job' && st.job === 'page' && (await badge()) === 'T3' && (await shown(now + '.ew-job-tool-summary')) && (await shown(after + '.ew-tool-card')));
  check('flow: the keyboard lands on the way back', (await focused()) === 'after/node/', await focused());
  check('T3 after: the card names the tool and the service', (await text(after + '.ew-tool-card-name')) === '기준 문서 확인사내 Confluence', await text(after + '.ew-tool-card-name'));
  check('T3 after: what the tool does, whole', (await text(after + '.ew-tool-card-purpose')) === '페이지 ID로 문서 제목과 문서 유형을 확인합니다.' && (await page.evaluate(s => { const e = document.querySelector(s); e.textContent = e.textContent.repeat(6); const whole = e.scrollHeight <= e.clientHeight + 1 && getComputedStyle(e).webkitLineClamp === 'none'; e.textContent = '페이지 ID로 문서 제목과 문서 유형을 확인합니다.'; return whole; }, after + '.ew-tool-card-purpose')));
  check('T3 after: 도구 변경 is in the card', await shown(after + '.ew-tool-card>[data-author-action=job_api_setup]'));
  const io = () => page.evaluate(s => { const d = document.querySelector(s + '.ew-tool-card-io'), first = [...d.querySelectorAll('dd')][0], lines = [...first.querySelectorAll(':scope>span')]; return { labels: [...d.querySelectorAll('dt')].map(e => e.textContent).join('|'), inputs: lines.length, pairs: lines.map(e => e.querySelector('b').textContent + '=' + e.querySelector(':scope>span:not(.ew-visually-hidden)').textContent).join('|'), read: first.textContent, results: [...d.querySelectorAll('dd')][1].textContent, inDetails: !!d.closest('details') }; }, after);
  let cardIo = await io();
  check('T3 after: what goes in and what comes back show at once', (await shown(after + '.ew-tool-card-io')) && cardIo.labels === '입력|받는 결과' && cardIo.pairs === '페이지 ID=실행 시 입력' && cardIo.results === '문서 제목, 페이지 ID, 문서 유형', JSON.stringify(cardIo));
  check('T3 after: the address and the result example are closed at first', !(await shown(after + '.ew-tool-card>details>dl')) && (await text(after + '.ew-tool-card>details>summary')) === '상세 보기');
  await page.click(after + '.ew-tool-card summary'); await page.waitForTimeout(150);
  check('T3 after: 상세 보기 opens those two and nothing else', (await shown(after + '.ew-tool-card>details>dl')) && (await page.locator(after + '.ew-tool-card>details dt').allTextContents()).join('|') === '주소|결과 예시');
  check('T3 after: the address is in the details', (await page.locator(after + '.ew-tool-card>details dd').first().textContent()) === 'GET /{id}');
  const baseline = await page.evaluate(s => { const dt = [...document.querySelectorAll(s + '.ew-tool-card dt')].pop(), b = document.querySelector(s + '.ew-tool-card [data-author-action=job_api_example]'); const range = document.createRange(); range.selectNodeContents(b); return Math.round(Math.abs(range.getBoundingClientRect().top - (() => { const r = document.createRange(); r.selectNodeContents(dt); return r.getBoundingClientRect().top; })())); }, after);
  check('T3 after: 예시 보기 sits on its label\'s line', baseline <= 1, baseline);
  const columns = await page.evaluate(s => [...document.querySelectorAll(s + '.ew-tool-card dd')].map(e => Math.round(e.getBoundingClientRect().left)), after);
  check('T3 after: the values shown and the values under 상세 보기 start on one edge', new Set(columns).size === 1, JSON.stringify(columns));
  await page.click(after + '.ew-tool-card [data-author-action=job_api_example]'); await page.waitForTimeout(80);
  check('T3 after: 예시 보기 says the product window would open', (await noteText()).includes('조회 결과 예시'));
  await page.click(after + '.ew-tool-card>[data-author-action=job_api_setup]'); await page.waitForTimeout(80);
  check('T3 after: 도구 변경 says the product window would open', (await noteText()).includes('도구를 고르는 창'));
  await page.click(after + '.ew-job-detail-header [data-author-action=node]'); await page.waitForTimeout(120);
  st = await state();
  check('flow: back from the job to the stage, open, on both sides', st.screen === 'proc' && st.open && (await badge()) === 'T2' && (await count(after + '.ew-job-row')) === 2 && (await count(now + '.ew-job-row')) === 2);
  check('flow: the now side comes back to the summary, as the product does', (await overview(now)) === 'true');
  check('flow: the keyboard is back on the job one came from', (await focused()) === 'after/node/page', await focused());

  // ---- T3 scene: the second job (two inputs, one from the earlier job)
  await show('T3');
  check('T3 now: the tool section lists inputs, results and address in the open', (await count(now + '.ew-job-tool-summary .ew-api-job-binding>*')) === 4);
  cardIo = await io();
  check('T3 after: each input is on its own line with where its value comes from', cardIo.inputs === 2 && cardIo.pairs === '페이지 ID=앞 작업 ‘기준 문서 확인’의 페이지 ID|표시할 문서 수=5' && !cardIo.inDetails, cardIo.pairs);
  check('T3 after: read aloud, the inputs do not run together', cardIo.read === '페이지 ID: 앞 작업 ‘기준 문서 확인’의 페이지 ID. 표시할 문서 수: 5. ', cardIo.read);
  check('T3 after: no separate line repeats the earlier job', (await count(after + '.ew-tool-card-link')) === 0);
  const sectionHeight = side => page.evaluate(s => Math.round(document.querySelector(s + '.ew-job-tool-summary').getBoundingClientRect().height), side);
  const heights = { now: await sectionHeight(now), after: await sectionHeight(after) };
  // recorded as it is: showing inputs and results at once costs height on the job page (revision 2, which folded them, was shorter than now)
  check('T3 after: with inputs and results shown the tool section is taller than now, by no more than 64px', heights.after > heights.now && heights.after <= heights.now + 64, JSON.stringify(heights));
  const card = await page.evaluate(s => { const c = document.querySelector(s + '.ew-tool-card').getBoundingClientRect(), b = document.querySelector(s + '.ew-tool-card>[data-author-action=job_api_setup]').getBoundingClientRect(), n = document.querySelector(s + '.ew-tool-card-name>span'), i = document.querySelector(s + 'input[name=name]'), r = document.createRange(); r.selectNodeContents(n); return { w: Math.round(c.width), button: [Math.round(b.width), Math.round(b.height)], text: Math.round(r.getBoundingClientRect().left - c.left), field: parseFloat(getComputedStyle(i).paddingLeft) + parseFloat(getComputedStyle(i).borderLeftWidth) }; }, after);
  check('T3 after: the card is as wide as what it holds (at most 640px), its text on the fields\' text edge', card.w <= 640 && card.text === card.field && card.button[1] === 32, JSON.stringify(card));
  await page.click(after + '.ew-tool-card summary'); await page.waitForTimeout(150);
  check('T3 after: the address of this job is under 상세 보기', (await page.locator(after + '.ew-tool-card>details dd').first().textContent()) === 'GET /{id}/child/page');
  await shot('T3-side-open');
  await page.click('[data-form-pick=now]'); await page.waitForTimeout(80);
  check('T3 option: the fields switch says it does not apply to a job page; what was open stays open', (await noteText()).includes('T1, T2, T4, T5') && (await shown(after + '.ew-tool-card>details>dl')), await noteText());
  await page.click('[data-form-pick=fold]'); await page.waitForTimeout(80);
  // keyboard: the details toggle is reachable and shows focus
  await page.focus(after + '.ew-tool-card summary'); await page.keyboard.press('Tab'); await page.keyboard.press('Shift+Tab');
  const ring = await page.evaluate(s => { const c = getComputedStyle(document.querySelector(s)); return c.outlineStyle + ' ' + c.outlineWidth; }, after + '.ew-tool-card summary');
  check('T3 after: 상세 보기 shows a focus ring from the keyboard', /solid 2px/.test(ring), ring);
  await page.keyboard.press('ArrowLeft'); await page.waitForTimeout(80);
  check('an arrow key pressed inside a side does not change what is shown', (await state()).view === 'now+after');
  await page.keyboard.press('Enter'); await page.waitForTimeout(100);
  check('T3 after: Enter closes the details; inputs and results stay', !(await shown(after + '.ew-tool-card>details>dl')) && (await shown(after + '.ew-tool-card-io')));
  await shot('T3-side');
  // the choice the agreement left to the user: inputs and results at once, or inside 상세 보기 as revision 2 had them
  await page.click('[data-card-pick=fold]'); await page.waitForTimeout(120);
  cardIo = await io();
  const folded = { now: await sectionHeight(now), after: await sectionHeight(after) };
  check('T3 option 상세 보기 안: the inputs and results are inside 상세 보기, closed at first, and the section is no taller than now', cardIo.inDetails && !(await shown(after + '.ew-tool-card-io')) && cardIo.pairs.includes('표시할 문서 수=5') && folded.after <= folded.now, JSON.stringify(folded));
  check('T3 option 상세 보기 안: the explanation says so', (await strip()).includes('모두 ‘상세 보기’ 안') && !(await strip()).includes('바로 보임'), await strip());
  await page.click(after + '.ew-tool-card summary'); await page.waitForTimeout(150);
  check('T3 option 상세 보기 안: opened, the four kinds are there in order on one edge', (await page.locator(after + '.ew-tool-card details dt').allTextContents()).join('|') === '입력|받는 결과|주소|결과 예시' && new Set(await page.evaluate(s => [...document.querySelectorAll(s + '.ew-tool-card dd')].map(e => Math.round(e.getBoundingClientRect().left)), after)).size === 1);
  await shot('T3-side-card-folded');
  await page.click('[data-card-pick=open]'); await page.waitForTimeout(120);
  check('T3 option 바로: back to inputs and results shown at once', !(await io()).inDetails && (await shown(after + '.ew-tool-card-io')) && (await strip()).includes('바로 보임'));

  // ---- T4: jobs that need a hand
  await show('T4');
  check('T4: such a procedure opens with its stage closed, in the summary today', (await badge()) === 'T4' && !(await state()).open && (await overview(now)) === 'true' && (await text(now.trim() + '>.mk-pane-label small')) === '요약 화면' && (await count(after + '.ew-job-row')) === 0);
  const foot = side => page.evaluate(s => { const f = document.querySelector(s + '#ees-work-designer footer, ' + s + 'footer'), st = f.querySelector('[data-author-status]'), save = f.querySelector('[data-author-action=save]'); return { text: st.textContent.trim(), status: st.getAttribute('data-status'), save: !save.disabled }; }, side);
  const feet = [await foot(now), await foot(after)];
  check('T4: the board is an unsaved draft on both sides (a draft with a deleted source job cannot be saved)', feet.every(f => f.text === '저장하지 않은 변경 있음' && f.status === 'dirty' && f.save), JSON.stringify(feet));
  const head = side => page.evaluate(s => { const n = document.querySelector(s + '.ew-stage-name'), t = n.querySelector('.ew-author-tag'), c = t ? getComputedStyle(t) : null; return { name: [...n.childNodes].filter(x => x.nodeType === 3).map(x => x.textContent).join('').trim(), chip: t ? t.textContent.trim() : '', count: document.querySelector(s + '.ew-stage-count').textContent.trim(), color: c ? c.color : '', bg: c ? c.backgroundColor : '', gap: c ? parseFloat(c.marginLeft) : 0, cut: n.scrollWidth > n.clientWidth + 1 }; }, side);
  const stageGap = () => markGap(after + '.ew-stage-name>.ew-author-tag');
  let stageNow = await head(now), stageAfter = await head(after);
  check('T4 now: the closed stage says nothing about the jobs that need a hand', stageNow.chip === '' && stageNow.count === '6개 작업', JSON.stringify(stageNow));
  check('T4 after: the closed stage says how many jobs need a hand', stageAfter.name === '문서 구조 확인' && stageAfter.chip === '손볼 작업 3개' && stageAfter.count === '6개 작업' && !stageAfter.cut, JSON.stringify(stageAfter));
  check('T4 after: that mark is a filled chip, readable, 8px after the stage name', stageAfter.bg !== 'rgba(0, 0, 0, 0)' && contrast(stageAfter.color, stageAfter.bg) >= 4.5 && (await stageGap()).gap === 8 && (await stageGap()).sameLine, JSON.stringify([stageAfter, await stageGap()]));
  await shot('T4-side');
  await page.click(after + '[data-author-action=stage_toggle]'); await page.waitForTimeout(150);
  const sumRows = await rows(now), board = await rows(after);
  stageAfter = await head(after);
  check('T4 after: the mark stays on the open stage and counts the marked jobs', stageAfter.chip === '손볼 작업 3개' && board.filter(r => r.chip).length === 3, JSON.stringify(board.map(r => r.chip)));
  check('T4 now: the summary has no mark on any job that needs a hand', sumRows.length === 6 && sumRows.every(r => !r.chip) && sumRows[3].action === '도구 연결', JSON.stringify(sumRows.map(r => [r.name, r.chip, r.action])));
  check('T4 now: a job whose source job is gone reads like any other', sumRows[5].bound.includes('페이지 ID ← 앞 작업에서 선택한 결과') && sumRows[1].bound.includes('페이지 ID ← 하위 문서 목록 조회에서 선택한 결과'), sumRows[5].bound);
  check('T4 after: six jobs, each its name and one line', board.length === 6 && board.every(r => !r.binding && r.h <= 64) && board.map(r => r.id).join(' ') === 'page digest children history owner notify', JSON.stringify(board.map(r => [r.id, r.h])));
  check('T4 after: a job fed by a job further down the list says 뒤 작업, one fed from above says 앞 작업', board[1].from === LATER && !board[1].chip && board[2].from === EARLIER && !board[2].chip, JSON.stringify([board[1].from, board[2].from]));
  check('T4 after: the job without a tool carries 도구 연결 전, the button 도구 연결, and does not yet say who confirms', board[3].name === '변경 이력 확인' && board[3].chip === '도구 연결 전' && board[3].action === '도구 연결' && board[3].actionName === '변경 이력 확인 도구 연결' && board[3].meta === '도구 사용', JSON.stringify(board[3]));
  check('T4 after: the job to check carries 도구 확인 필요', board[4].name === '담당자 정보 조회' && board[4].chip === '도구 확인 필요' && !board[4].action && board[4].meta === META);
  check('T4 after: the job whose source job is gone carries 입력 확인 필요 and says why', board[5].name === '변경 알림 대상 조회' && board[5].chip === '입력 확인 필요' && board[5].from === GONE && board[5].meta === META, JSON.stringify(board[5]));
  const chips = await page.evaluate(s => [...document.querySelectorAll(s + '.ew-job-row .ew-author-tag[data-tool-state]')].map(e => { const c = getComputedStyle(e); return { color: c.color, bg: c.backgroundColor, radius: c.borderTopLeftRadius, h: Math.round(e.getBoundingClientRect().height) }; }), after);
  const gaps = []; for (const id of ['history', 'owner', 'notify']) gaps.push(await markGap(after + `.ew-job-row[data-job-id=${id}] .ew-author-tag[data-tool-state]`));
  check('T4 after: each mark is a filled chip, not a colour of the text alone, 8px after the name', chips.length === 3 && chips.every(c => c.bg !== 'rgba(0, 0, 0, 0)' && contrast(c.bg, 'rgb(255,255,255)') >= 1.08 && c.radius !== '0px') && gaps.every(g => g.gap === 8 && g.sameLine), JSON.stringify([chips, gaps]));
  // a name long enough to push its mark to the next line: the mark starts on the name's edge
  const wrapped = await page.evaluate(s => { const row = document.querySelector(s + '.ew-job-row[data-job-id=history]'), name = row.querySelector('.ew-job-row-label>span'), node = [...name.childNodes].find(n => n.nodeType === 3), was = node.textContent; node.textContent = '변경 이력 확인 '.repeat(14).trim(); const tag = name.querySelector('.ew-author-tag').getBoundingClientRect(), range = document.createRange(); range.selectNodeContents(node); const rects = [...range.getClientRects()], out = { lines: rects.length, under: tag.top >= rects[rects.length - 1].bottom - 2, left: Math.round(tag.left - rects[0].left), rowOver: row.scrollWidth - row.clientWidth }; node.textContent = was; return out; }, after);
  check('T4 after: a mark that wraps under a long name starts on the name\'s edge', wrapped.lines >= 2 && (!wrapped.under || wrapped.left === 0) && wrapped.rowOver <= 0, JSON.stringify(wrapped));
  check('T4 after: the chip text is readable on the chip', chips.every(c => contrast(c.color, c.bg) >= 4.5), chips.map(c => contrast(c.color, c.bg).toFixed(2)).join(' '));
  const goneTone = await page.evaluate(s => getComputedStyle(document.querySelector(s + '.ew-job-from[data-from=gone]')).color, after);
  check('T4 after: the reason is readable in the attention tone', contrast(goneTone, 'rgb(255,255,255)') >= 4.5 && goneTone === chips[0].color, goneTone);
  const place = await page.evaluate(s => { const row = document.querySelector(s + '.ew-job-row[data-job-id=history]'), a = row.querySelector('.ew-api-row-action'), b = a.getBoundingClientRect(), r = row.getBoundingClientRect(), m = row.querySelector('.ew-job-menu-button'), mb = m.getBoundingClientRect(), tag = row.querySelector('.ew-author-tag').getBoundingClientRect(); return { inRow: b.top >= r.top && b.bottom <= r.bottom, gap: Math.round(mb.left - b.right), clear: Math.round(b.left - tag.right), rowH: Math.round(r.height), h: Math.round(b.height), domBeforeMenu: !!(a.compareDocumentPosition(m) & Node.DOCUMENT_POSITION_FOLLOWING) }; }, after);
  check('T4 after: 도구 연결 sits on the job row, left of ⋯, clear of the text, 32px tall', place.inRow && place.gap >= 4 && place.gap <= 16 && place.clear > 8 && place.rowH <= 64 && place.h === 32, JSON.stringify(place));
  check('T4 after: the keyboard reaches 도구 연결 before ⋯, as the eye does', place.domBeforeMenu);
  // the three jobs that need a hand are the last three: bring them into view on both sides for the picture
  await page.evaluate(() => document.querySelectorAll('.mk-pane .ew-job-row[data-job-id=notify]').forEach(r => r.scrollIntoView({ block: 'end' }))); await page.waitForTimeout(100);
  check('T4 after: the three jobs that need a hand fit in view together', (await inView(after)).slice(3).every(Boolean), JSON.stringify(await inView(after)));
  await shot('T4-side-open');
  const listScroll = side => page.evaluate(s => Math.round(document.querySelector(s + '.ew-author-scroll').scrollTop), side);
  const before = await listScroll(after);
  await page.focus(after + '[data-author-action=node][data-id=notify]'); await page.keyboard.press('Enter'); await page.waitForTimeout(150);
  const gonePage = await page.evaluate(s => { const c = document.querySelector(s + '.ew-tool-card'), v = c.querySelector('.ew-tool-card-io [data-from=gone]'); return { name: c.querySelector('.ew-tool-card-name>span').textContent, chip: (c.querySelector('.ew-tool-card-name .ew-author-tag') || { textContent: '' }).textContent, input: c.querySelector('.ew-tool-card-io b').textContent, source: v ? v.textContent : '', tone: v ? getComputedStyle(v).color : '', action: c.querySelector(':scope>[data-author-action=job_api_setup]').textContent }; }, after);
  check('T4-3 after: the job whose source job is gone — its page keeps the tool, says 입력 확인 필요, marks the input that lost its source, and offers 도구 변경', (await badge()) === 'T4-3' && gonePage.name === '기준 문서 확인' && gonePage.chip === '입력 확인 필요' && gonePage.input === '페이지 ID' && gonePage.source === GONE && contrast(gonePage.tone, 'rgb(255,255,255)') >= 4.5 && gonePage.action === '도구 변경', JSON.stringify(gonePage));
  check('T4-3 now: the product keeps the link and writes 앞 작업 and the raw field name', (await text(now + '.ew-job-tool-summary .ew-api-job-binding>div')) === '페이지 ID ← 앞 작업 · id' && (await page.inputValue(now + 'input[name=name]')) === '변경 알림 대상 조회', await text(now + '.ew-job-tool-summary .ew-api-job-binding>div'));
  await shot('T4-3-job-input-gone');
  await page.keyboard.press('Enter'); await page.waitForTimeout(150);
  const back = { scroll: await listScroll(after), focus: await focused(), seen: await page.evaluate(s => { const e = document.activeElement.getBoundingClientRect(), sc = document.querySelector(s + '.ew-author-scroll').getBoundingClientRect(); return e.top >= sc.top - 1 && e.bottom <= sc.bottom + 1; }, after) };
  check('T4: back from a job by the keyboard, the list is where one left it and the job one came from is in view with the focus on it', (await badge()) === 'T4' && back.scroll === before && back.focus === 'after/node/notify' && back.seen, JSON.stringify([before, back]));
  await page.click(after + '[data-author-action=node][data-id=digest]'); await page.waitForTimeout(120);
  check('T4-4 after: the job fed by a later job — its card says which job the input comes from', (await badge()) === 'T4-4' && (await io()).pairs === '페이지 ID=뒤 작업 ‘하위 문서 목록 조회’의 페이지 ID' && (await count(after + '.ew-tool-card-name .ew-author-tag')) === 0 && (await text(now + '.ew-job-tool-summary .ew-api-job-binding>div')) === '페이지 ID ← 하위 문서 목록 조회 · 페이지 ID', (await io()).pairs);
  await page.click(after + '.ew-job-detail-header [data-author-action=node]'); await page.waitForTimeout(120);
  await page.click(now + '.ew-procedure-menu>summary'); await page.waitForTimeout(100);
  await page.click(now + '[data-author-action=api_structure_edit]'); await page.waitForTimeout(120);
  const editRows = await rows(now);
  const nowPlace = await page.evaluate(s => { const row = document.querySelector(s + '.ew-job-row[data-job-id=history]'), b = row.querySelector('.ew-api-row-action').getBoundingClientRect(), a = row.querySelector('.ew-author-job').getBoundingClientRect(); return { below: b.top >= a.bottom - 1, tag: (row.querySelector('.ew-procedure-unconnected') || { textContent: '' }).textContent }; }, now);
  check('T4 now: after 절차 편집 the job without a tool has a grey mark and 도구 연결 on a line of its own', editRows.length === 6 && nowPlace.below && nowPlace.tag === '도구 연결 전', JSON.stringify(nowPlace));
  check('T4 now: after 절차 편집 the stage row still has no mark', (await head(now)).chip === '');
  await shot('T4-side-now-edit');
  await page.click(after + '[data-author-action=node][data-id=history]'); await page.waitForTimeout(120);
  check('T4-1 after: the job without a tool — its page shows the same mark and one button, 도구 연결', (await badge()) === 'T4-1' && (await text(after + '.ew-tool-card-name')) === '도구 연결 전' && (await text(after + '.ew-tool-card>[data-author-action=job_api_setup]')) === '도구 연결' && (await count(after + '.ew-tool-card details')) === 0 && (await count(after + '.ew-tool-card-io')) === 0);
  const connect = await page.evaluate(s => { const b = document.querySelector(s + '.ew-tool-card>[data-author-action=job_api_setup]').getBoundingClientRect(), c = document.querySelector(s + '.ew-tool-card').getBoundingClientRect(), t = document.querySelector(s + '.ew-tool-card .ew-author-tag').getBoundingClientRect(); return { h: Math.round(b.height), right: Math.round(c.right - b.right), mid: Math.round(Math.abs((b.top + b.bottom) / 2 - (t.top + t.bottom) / 2)), cardH: Math.round(c.height) }; }, after);
  check('T4-1 after: the button is where 도구 변경 is on a connected job, the same size', connect.h === 32 && connect.right === 13 && connect.mid <= 1, JSON.stringify(connect));
  await shot('T4-1-job-unconnected');
  await page.click(after + '.ew-job-detail-header [data-author-action=node]'); await page.waitForTimeout(120);
  check('T4: back to the board, open', (await badge()) === 'T4' && (await count(after + '.ew-job-row')) === 6);
  await page.click(after + '[data-author-action=node][data-id=owner]'); await page.waitForTimeout(120);
  check('T4-2 after: the job to check — its page says so and offers 도구 변경', (await badge()) === 'T4-2' && (await text(after + '.ew-tool-card-name')) === '도구 확인 필요' && (await text(after + '.ew-tool-card-purpose')) === '연결한 도구의 현재 사용 권한을 확인해 주세요.' && (await shown(after + '.ew-tool-card>[data-author-action=job_api_setup]')) && (await count(after + '.ew-tool-card details')) === 0);
  await shot('T4-2-job-review');
  await page.click(after + '.ew-job-detail-header [data-author-action=node]'); await page.waitForTimeout(120);
  await page.click(after + '[data-author-action=list]'); await page.waitForTimeout(120);
  check('T4: the list counts the board\'s six jobs', (await page.evaluate(s => [...document.querySelectorAll(s + '[data-author-action=open]')].find(x => x.textContent.includes('Confluence')).textContent, after)).includes('작업 6'));

  // ---- T5: a procedure with people's jobs and a tool job
  await show('T5');
  const mixNow = await rows(now), mixAfter = await rows(after);
  check('T5 now: the person\'s job is two lines, the tool job has the note under it', (await badge()) === 'T5' && mixNow.length === 2 && mixNow[0].lines === 2 && mixNow[1].binding && mixNow[1].lines >= 5, JSON.stringify(mixNow.map(r => r.lines)));
  check('T5 after: both jobs are a name and one line', mixAfter.length === 2 && mixAfter.every(r => r.lines === 2 && !r.binding && !r.action && !r.chip && !r.from), JSON.stringify(mixAfter));
  check('T5 after: the person\'s job reads as it does now', mixAfter[0].name === mixNow[0].name && mixAfter[0].meta === mixNow[0].meta && mixAfter[0].h === mixNow[0].h, mixAfter[0].meta);
  check('T5 after: the tool job keeps its name and the line it has now', mixAfter[1].name === '점검 기준 문서 찾기' && mixAfter[1].meta === META && mixNow[1].meta === META);
  check('T5 after: the two rows are the same height', mixAfter[0].h === mixAfter[1].h, mixAfter.map(r => r.h).join(' '));
  check('T5: this kind of procedure has the fields open today; after, they are folded and the line says its purpose', (await fields(now)) && !(await fields(after)) && (await page.locator(after + '.ew-procedure-brief>span').allTextContents()).join('|') === '업무 분류 운영|업무 목적 매주 월요일 설비 상태를 확인하고 이상을 기록합니다.');
  check('T5 after: no stage carries a mark when no job needs a hand', (await count(after + '.ew-stage-name .ew-author-tag')) === 0);
  await shot('T5-side');
  await page.click(after + '[data-author-action=node][data-id=checks]'); await page.waitForTimeout(80);
  check('T5: a person\'s job says its page does not change and stays put', (await noteText()).includes('사람이 하는 작업') && (await state()).screen === 'proc');
  await page.click(after + '[data-author-action=node][data-id=doc]'); await page.waitForTimeout(120);
  check('T5-1 after: the tool job\'s page has the card — here the tool\'s name differs from the job\'s', (await badge()) === 'T5-1' && (await text(after + '.ew-tool-card-name')) === '기준 문서 확인사내 Confluence' && (await page.inputValue(after + 'input[name=name]')) === '점검 기준 문서 찾기');
  await page.click(after + '.ew-job-detail-header [data-author-action=node]'); await page.waitForTimeout(120);
  check('T5: back to the mixed procedure, open', (await state()).mixed && (await count(after + '.ew-job-row')) === 2);
  await page.click(now + '[data-author-action=stage_toggle][data-id=record]'); await page.waitForTimeout(80);
  check('T5: the second stage says the mock opens only the first', (await noteText()).includes('첫 단계만'));

  // ---- which sides are shown
  await show('T2');
  await page.click('[data-pane-pick=now]'); await page.waitForTimeout(100);
  check('sides: 지금 can be turned off; the proposal alone shows the whole window, with its left menu', (await state()).view === 'after' && !(await shown(now + '#ees-work-panel')) && (await shown(after + '.fu-side')));
  if (width >= 1200) check('single view: the chat shows from 1200', await shown(after + '.fu-chat'));
  await page.click('[data-pane-pick=after]'); await page.waitForTimeout(100);
  check('sides: the last one stays on', (await state()).view === 'after' && (await noteText()).includes('하나는'));
  await shot('T2-after');
  await page.evaluate(() => document.activeElement && document.activeElement.blur());
  await page.keyboard.press('ArrowLeft'); await page.waitForTimeout(100);
  check('single view: ← shows now', (await state()).view === 'now' && (await shown(now + '.fu-side')));
  await page.click('[data-form-pick=now]'); await page.waitForTimeout(80);
  check('single view: the switch says it only touches the proposal when only now is shown', (await noteText()).includes('‘바꾼 뒤’ 쪽에만'), await noteText());
  await page.click('[data-card-pick=fold]'); await page.waitForTimeout(80);
  check('a switch with nothing to change on this screen says where it shows', (await noteText()).includes('T3'), await noteText());
  await page.click('[data-card-pick=open]');
  await page.click('[data-form-pick=fold]');
  await page.keyboard.press('ArrowRight'); await page.waitForTimeout(100);
  check('single view: → shows the proposal again', (await state()).view === 'after');
  await page.keyboard.press('5'); await page.waitForTimeout(100);
  check('keys 1–5 pick the screen', (await state()).where === 'T5');

  // ---- things the mock does not do say so; where one had scrolled to is kept
  await show('T2');
  await page.click(after + '[data-author-action=add_job]'); await page.waitForTimeout(80);
  check('a press the mock does not act on says it works as the product does', (await noteText()).includes('지금 제품과 같은 동작') && (await state()).screen === 'proc');
  const noteBox = await page.evaluate(() => { const n = document.querySelector('#mock-note').getBoundingClientRect(), l = [...document.querySelectorAll('.mk-pane-label')].map(e => e.getBoundingClientRect().bottom); return { top: Math.round(n.top), labels: Math.round(Math.max(...l)), bottom: Math.round(innerHeight - n.bottom) }; });
  check('the note sits at the bottom, clear of the side headings', noteBox.top > noteBox.labels + 100 && noteBox.bottom >= 60, JSON.stringify(noteBox));
  await show('T4');   // the longest of the screens, so there is something to scroll at either window size
  await page.click(after + '[data-author-action=stage_toggle]'); await page.waitForTimeout(120);
  const scrolled = await page.evaluate(s => { const e = document.querySelector(s + '.ew-author-scroll'); e.scrollTop = 60; return e.scrollTop; }, after);
  await page.click('[data-form-pick=now]'); await page.waitForTimeout(120);
  const kept = await page.evaluate(s => document.querySelector(s + '.ew-author-scroll').scrollTop, after);
  check('the switch above redraws the side without losing where one had scrolled to', scrolled > 0 && kept === scrolled, scrolled + ' → ' + kept);
  await page.click('[data-form-pick=fold]');

  // ---- nothing runs off the side; text is not cut
  for (const scene of ['T1', 'T2', 'T3', 'T4', 'T5']) for (const form of ['fold', 'now', 'open']) {
    await show(scene, 'side', form === 'open' ? 'fold' : form, scene === 'T3' && form === 'now' ? 'fold' : 'open');
    if (scene === 'T4') { await page.click(after + '[data-author-action=stage_toggle]'); await page.waitForTimeout(100); }
    if (form === 'open') { if (scene === 'T3') continue; await page.click(after + '.ew-procedure-brief [data-author-action=info_toggle]'); await page.waitForTimeout(100); }
    if (scene === 'T3') await page.evaluate(() => document.querySelectorAll('.mk-pane[data-side=after] .ew-tool-card details').forEach(d => { d.open = true; }));
    const over = await page.evaluate(() => [...document.querySelectorAll('.mk-pane')].map(p => { const s = p.querySelector('.ew-author-scroll') || p.querySelector('#ees-work-panel'); return s.scrollWidth - s.clientWidth; }));
    check(`${scene} (fields ${form}): no sideways scroll in either side`, over.every(v => v <= 0), JSON.stringify(over));
    const cut = await page.evaluate(() => [...document.querySelectorAll('.mk-pane[data-side=after] :is(.ew-job-row-label>span,.ew-job-meta,.ew-stage-name,.ew-procedure-brief>span,.ew-procedure-brief>button,.ew-tool-card-name,.ew-tool-card dd,.ew-tool-card dd>span>b,.ew-api-row-action,.ew-tool-card button,.ew-author-tag)')].filter(e => e.getBoundingClientRect().width > 0 && (e.scrollWidth > e.clientWidth + 1)).map(e => e.textContent.trim().slice(0, 20)));
    check(`${scene} (fields ${form}): no cut text on the after side`, cut.length === 0, JSON.stringify(cut));
  }
  // ---- the guide: the reference line and folding
  await show('T2');
  check('the explanation names what changes, not two proposals', (await page.locator('#mock-step-text b').allTextContents()).join('|') === '언제|바뀌는 것');
  check('T2: the explanation does not send 입력 연결 변경 to a place where it is not', (await strip()).includes('‘입력 연결 변경’은 없어짐'), await strip());
  check('the reference line is closed until asked for', !(await page.locator('#mock-step-text').textContent()).includes('참고'));
  await page.click('#mock-ref-toggle'); await page.waitForTimeout(80);
  check('참고 opens the reference line: what is the product\'s own, which rows were written by hand, where the other proposal is', (await page.locator('#mock-step-text').textContent()).includes('main 598440d') && (await strip()).includes('제품 코드에서 옮겨 적은') && (await strip()).includes('저장하지 않은 편집 중') && (await strip()).includes('‘보기 먼저’ 안은 2판'));
  await page.click('#mock-ref-toggle');
  await page.click('#mock-fold'); await page.waitForTimeout(80);
  check('the explanation folds; the badge and the buttons stay', (await shown('#mock-badge')) && (await shown('[data-step=T1]')) && (await shown('[data-form-pick=fold]')) && (await shown('[data-card-pick=open]')) && !(await shown('#mock-step-text')) && !(await shown('#mock-ref-toggle')));
  await page.click('#mock-fold');
  check('no page errors', errors.length === 0, JSON.stringify(errors));
  await page.close();
}

(async () => {
  const browser = await chromium.launch();
  await run(browser, 1920, 1080); await run(browser, 1366, 768);
  await browser.close();
  const failed = results.filter(r => !r.ok);
  fs.writeFileSync(reportPath, JSON.stringify({ mock: path.basename(file), revision: 3, checks: results.length, passed: results.length - failed.length, failed: failed.length, results }, null, 1));
  console.log(`checks ${results.length} passed ${results.length - failed.length} failed ${failed.length}`);
  for (const r of failed) console.log('FAIL', r.size, r.name, r.detail);
})();
