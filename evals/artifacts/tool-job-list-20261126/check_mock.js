// Browser check of design mock 23 (tool job list): walks the flow in both versions and checks what shows.
// usage: node check_mock.js MOCK.html REPORT.json [SHOTDIR]
const { chromium } = require('playwright');
const fs = require('fs'); const path = require('path');
const [file, reportPath, shotDir] = process.argv.slice(2);
const results = []; let current = '';
const check = (name, ok, detail) => { results.push({ size: current, name, ok: !!ok, detail: detail === undefined ? '' : String(detail) }); };
const lum = c => { const m = c.match(/[\d.]+/g).map(Number); const f = v => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }; return .2126 * f(m[0]) + .7152 * f(m[1]) + .0722 * f(m[2]); };
const contrast = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05); };
const META = '도구 사용 · 담당자 확인', FROM = '‘기준 문서 확인’ 결과 사용';

async function run(browser, width, height) {
  current = width + 'x' + height;
  const page = await browser.newPage({ viewport: { width, height } });
  const errors = []; page.on('pageerror', e => errors.push(String(e))); page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  await page.goto('file://' + path.resolve(file)); await page.evaluate(() => document.fonts.ready);
  const now = '.mk-pane[data-side=now] ', after = '.mk-pane[data-side=after] ', view = '.mk-pane[data-side=view] ';
  const show = async (scene, view, mark, form) => { await page.evaluate(([s, v, m, f]) => window.mockShow(s, v, m, f), [scene, view || 'side', mark || 'on', form || 'on']); await page.waitForTimeout(120); };
  // a closed <details> keeps its content's boxes (content-visibility), so ask the browser whether it is rendered
  const shown = sel => page.evaluate(s => { const e = document.querySelector(s); if (!e) return false; const c = getComputedStyle(e), r = e.getBoundingClientRect(); return c.display !== 'none' && c.visibility !== 'hidden' && r.width > 1 && r.height > 1 && e.checkVisibility(); }, sel);
  const text = sel => page.evaluate(s => { const e = document.querySelector(s); return e ? e.textContent.trim() : null; }, sel);
  const count = sel => page.locator(sel).count();
  const state = () => page.evaluate(() => window.mockState());
  const badge = async () => (await text('#mock-badge')).split(' · ').pop();
  const noteText = () => page.evaluate(() => document.querySelector('#mock-note').textContent);
  const focused = () => page.evaluate(() => { const e = document.activeElement; return e ? [(e.closest('.mk-pane') || { getAttribute: () => '' }).getAttribute('data-side'), e.getAttribute('data-author-action') || e.tagName, e.getAttribute('data-id') || ''].join('/') : ''; });
  const shot = async name => { if (shotDir) { await page.waitForTimeout(3300); await page.screenshot({ path: path.join(shotDir, `${name}-${width}.png`) }); } };
  const rows = side => page.evaluate(s => [...document.querySelectorAll(s + '.ew-job-row')].map(r => { const name = r.querySelector('.ew-job-row-label>span'), tag = name.querySelector('.ew-author-tag'); return { id: r.getAttribute('data-job-id'), h: Math.round(r.getBoundingClientRect().height), name: [...name.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join('').trim(), chip: tag ? tag.textContent.trim() : '', meta: [...r.querySelectorAll('.ew-job-meta')].map(m => m.innerText.trim()).join(''), lines: r.innerText.split('\n').map(x => x.trim()).filter(Boolean).length, binding: !!r.querySelector('[data-api-job-binding]'), action: (r.querySelector('.ew-api-row-action') || { textContent: '' }).textContent.trim() }; }), side);
  const overview = side => page.evaluate(s => document.querySelector(s + '#ees-work-designer').getAttribute('data-api-overview'), side);

  check('a wide window opens with all three sides, a narrower one with the two proposals', (await state()).view === (width >= 1600 ? 'now+after+view' : 'after+view'), (await state()).view);
  check('a short window starts with the explanation folded, a tall one open', (await page.evaluate(() => document.querySelector('#mock-guide').getAttribute('data-collapsed'))) === String(height < 900));
  if (height < 900) {
    check('folded: the screens and the two switches are still there to press', (await shown('[data-step=T4]')) && (await shown('[data-form-pick=off]')) && (await shown('[data-mark-pick=off]')) && !(await shown('#mock-step-text')));
    await page.click('[data-form-pick=off]'); await page.waitForTimeout(120);
    check('folded: the fields switch works without opening the explanation', !(await shown(after + 'input[name=overview_name]')));
    await page.click('[data-form-pick=on]'); await page.waitForTimeout(120);
    await show('T4');
    const seen = await page.evaluate(s => { const sc = document.querySelector(s + '.ew-author-scroll').getBoundingClientRect(); return [...document.querySelectorAll(s + '.ew-job-row')].map(r => { const b = r.getBoundingClientRect(); return b.top >= sc.top - 1 && b.bottom <= sc.bottom + 1; }); }, after);
    check('folded: the four jobs of T4 are in view on the after side', seen.length === 4 && seen.every(Boolean), JSON.stringify(seen));
    await page.click('#mock-fold');
  }

  // ---- T1: the procedure as it opens
  await show('T1');
  check('T1 badge says it is a mock and names the screen', (await text('#mock-badge')) === '시안 2 · 저장·실행 안 됨 · T1');
  check('T1 now: the summary hides 단계 추가', (await overview(now)) === 'true' && !(await shown(now + '[data-author-action=add_stage]')));
  check('T1 now: the way in is ⋯ → 절차 편집', (await text(now + '[data-author-action=api_structure_edit]')) === '절차 편집');
  check('T1 after: 단계 추가 shows as the procedure opens', await shown(after + '[data-author-action=add_stage]'));
  check('T1 after: no 절차 편집 / 도구 연결 보기 in the menu', (await count(after + '[data-author-action=api_structure_edit]')) === 0);
  check('T1 after: the other menu items stay', (await page.locator(after + '.ew-procedure-menu button').allTextContents()).join('|') === '업무 절차 정보·분류 수정|다른 이름으로 저장|내용 확인|게시 내림');
  check('T1 after: the name, category and purpose fields show, as the product has them today', await shown(after + 'input[name=overview_name]'));
  const listTop = side => page.evaluate(s => Math.round(document.querySelector(s + '.ew-stage-list').getBoundingClientRect().top - document.querySelector(s + '#ees-work-panel').getBoundingClientRect().top), side);
  const tops = { now: await listTop(now), on: await listTop(after) };
  await shot('T1-side');
  await page.click('[data-form-pick=off]'); await page.waitForTimeout(120);
  tops.off = await listTop(after);
  check('T1 option: with the fields folded the stage list starts about where the summary has it', !(await shown(after + 'input[name=overview_name]')) && tops.off < tops.on - 150 && Math.abs(tops.off - tops.now) <= 80, JSON.stringify(tops));
  check('T1 option: the name and category are still reachable from the ⋯ menu', (await page.locator(after + '.ew-procedure-menu button').allTextContents()).includes('업무 절차 정보·분류 수정'));
  check('T1 option: the now side does not change', !(await shown(now + 'input[name=overview_name]')) && (await listTop(now)) === tops.now);
  await shot('T1-side-form-folded');
  await page.click('[data-form-pick=on]'); await page.waitForTimeout(120);
  await page.click('[data-mark-pick=off]'); await page.waitForTimeout(80);
  check('an option with nothing to change on this screen says where it shows', (await noteText()).includes('T2, T3, T4'), await noteText());
  await page.click('[data-mark-pick=on]');

  // ---- T2: a stage open
  await show('T2');
  const nowRows = await rows(now), afterRows = await rows(after);
  check('T2 now: each job shows its name and three more lines', nowRows.length === 2 && nowRows.every(r => r.binding && r.lines >= 4), JSON.stringify(nowRows.map(r => r.lines)));
  check('T2 after: each job is its name and one line, nothing under it', afterRows.length === 2 && afterRows.every(r => !r.binding && !r.action && !r.chip && r.lines === 2), JSON.stringify(afterRows));
  check('T2 after: the line is the one the product writes today', afterRows[0].meta === META, afterRows[0].meta);
  check('T2 after: the job that takes an earlier result names that job', afterRows[1].meta === META + ' · ' + FROM, afterRows[1].meta);
  check('T2 after: a job row is at most 64px tall', afterRows.every(r => r.h <= 64), JSON.stringify(afterRows.map(r => r.h)));
  check('T2 after: rows are shorter than now', afterRows.reduce((a, r) => a + r.h, 0) < nowRows.reduce((a, r) => a + r.h, 0), afterRows.reduce((a, r) => a + r.h, 0) + ' < ' + nowRows.reduce((a, r) => a + r.h, 0));
  check('T2 after: 작업 추가 and 단계 추가 show', (await shown(after + '[data-author-action=add_job]')) && (await shown(after + '[data-author-action=add_stage]')));
  check('T2 now: 작업 추가 and 단계 추가 are hidden in the summary', !(await shown(now + '[data-author-action=add_job]')) && !(await shown(now + '[data-author-action=add_stage]')));
  const inView = side => page.evaluate(s => { const sc = document.querySelector(s + '.ew-author-scroll').getBoundingClientRect(); return [...document.querySelectorAll(s + '.ew-job-row')].map(r => { const b = r.getBoundingClientRect(); return b.top >= sc.top - 1 && b.bottom <= sc.bottom + 1; }); }, side);
  check('T2: the jobs are in view on both sides without scrolling by hand', (await inView(now)).every(Boolean) && (await inView(after)).every(Boolean), JSON.stringify([await inView(now), await inView(after)]));
  await shot('T2-side');
  await page.click('[data-mark-pick=off]'); await page.waitForTimeout(100);
  check('T2 option: without the mark the second job reads like the first', (await rows(after))[1].meta === META);
  await shot('T2-side-no-mark');
  await page.click('[data-mark-pick=on]'); await page.waitForTimeout(100);
  // now side: ⋯ → 절차 편집 shows today's edit view with the note boxes
  await page.click(now + '.ew-procedure-menu>summary'); await page.waitForTimeout(100);
  await page.click(now + '[data-author-action=api_structure_edit]'); await page.waitForTimeout(120);
  check('T2 now: after 절차 편집 the edit view shows, with the note under each job', (await overview(now)) === 'false' && (await shown(now + '[data-author-action=add_stage]')) && (await count(now + '.ew-job-row>.ew-api-job-binding')) === 2);
  check('T2 now: the edit view writes the same line the after side keeps', (await rows(now))[0].meta === META);
  check('T2 now: the caption says which of the two views this is', (await text(now.trim() + '>.mk-pane-label small')) === '⋯ → 절차 편집을 누른 뒤');
  await show('T2');

  // ---- the flow: list → procedure → stage → job → details → back
  await page.click(after + '[data-author-action=list]'); await page.waitForTimeout(120);
  check('flow: back to the list on both sides, numbered T0', (await state()).screen === 'list' && (await badge()) === 'T0' && (await shown(now + '[data-author-action=create]')) && (await shown(after + '[data-author-action=create]')));
  await page.evaluate(sel => { const e = [...document.querySelectorAll(sel + '[data-author-action=open]')].find(x => !x.textContent.includes('Confluence')); e && e.click(); }, after); await page.waitForTimeout(120);
  check('flow: the other procedure (people and a tool) opens in the edit view on both sides', (await state()).mixed && (await badge()) === 'T5' && (await shown(now + '[data-author-action=add_stage]')) && (await shown(after + '[data-author-action=add_stage]')) && (await text('h2')) === '주간 설비 점검');
  await page.click(after + '[data-author-action=list]'); await page.waitForTimeout(120);
  await page.evaluate(sel => { const e = [...document.querySelectorAll(sel + '[data-author-action=open]')].find(x => x.textContent.includes('Confluence')); e && e.click(); }, after); await page.waitForTimeout(120);
  check('flow: the guide opens — summary now, edit view after', (await badge()) === 'T1' && (await overview(now)) === 'true' && (await shown(after + '[data-author-action=add_stage]')));
  await page.click(after + '[data-author-action=stage_toggle]'); await page.waitForTimeout(120);
  check('flow: opening the stage on one side opens it on the other, and the badge follows', (await badge()) === 'T2' && (await count(now + '.ew-job-row')) === 2 && (await count(after + '.ew-job-row')) === 2);
  check('flow: the keyboard stays on the stage row that was pressed', (await focused()) === 'after/stage_toggle/documents', await focused());
  await page.click(after + '[data-author-action=node][data-id=page]'); await page.waitForTimeout(120);
  let st = await state();
  check('flow: a job row opens the job page on both sides', st.screen === 'job' && st.job === 'page' && (await badge()) === 'T3' && (await shown(now + '.ew-job-tool-summary')) && (await shown(after + '.ew-tool-card')));
  check('flow: the keyboard lands on the way back', (await focused()) === 'after/node/', await focused());
  check('T3 after: the card names the tool and the service', (await text(after + '.ew-tool-card-name')) === '기준 문서 확인사내 Confluence', await text(after + '.ew-tool-card-name'));
  check('T3 after: one line of what the tool does', (await text(after + '.ew-tool-card-purpose')) === '페이지 ID로 문서 제목과 문서 유형을 확인합니다.');
  check('T3 after: a job that takes nothing from an earlier job has no such line', (await count(after + '.ew-tool-card-link')) === 0);
  check('T3 after: 도구 변경 is in the card', await shown(after + '.ew-tool-card>[data-author-action=job_api_setup]'));
  check('T3 after: inputs, results and address are closed at first', !(await shown(after + '.ew-tool-card dl')));
  await page.click(after + '.ew-tool-card summary'); await page.waitForTimeout(150);
  check('T3 after: 상세 보기 opens them', (await shown(after + '.ew-tool-card dl')) && (await page.locator(after + '.ew-tool-card dt').allTextContents()).join('|') === '입력|받는 결과|주소|결과 예시');
  check('T3 after: the address is in the details', (await page.locator(after + '.ew-tool-card dd').nth(2).textContent()) === 'GET /{id}');
  const baseline = await page.evaluate(s => { const dt = [...document.querySelectorAll(s + '.ew-tool-card dt')].pop(), b = document.querySelector(s + '.ew-tool-card [data-author-action=job_api_example]'); const range = document.createRange(); range.selectNodeContents(b); return Math.round(Math.abs(range.getBoundingClientRect().top - (() => { const r = document.createRange(); r.selectNodeContents(dt); return r.getBoundingClientRect().top; })())); }, after);
  check('T3 after: 예시 보기 sits on its label\'s line', baseline <= 1, baseline);
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
  const sectionHeight = side => page.evaluate(s => Math.round(document.querySelector(s + '.ew-job-tool-summary').getBoundingClientRect().height), side);
  check('T3 after: the tool section is not taller than now when closed', (await sectionHeight(after)) <= (await sectionHeight(now)), (await sectionHeight(after)) + ' <= ' + (await sectionHeight(now)));
  check('T3 after: the card says which job its input comes from', (await text(after + '.ew-tool-card-link')) === FROM && (await shown(after + '.ew-tool-card-link')));
  const card = await page.evaluate(s => { const c = document.querySelector(s + '.ew-tool-card').getBoundingClientRect(), b = document.querySelector(s + '.ew-tool-card>[data-author-action=job_api_setup]').getBoundingClientRect(), n = document.querySelector(s + '.ew-tool-card-name>span'), i = document.querySelector(s + 'input[name=name]'), r = document.createRange(); r.selectNodeContents(n); return { w: Math.round(c.width), button: [Math.round(b.width), Math.round(b.height)], text: Math.round(r.getBoundingClientRect().left - c.left), field: parseFloat(getComputedStyle(i).paddingLeft) + parseFloat(getComputedStyle(i).borderLeftWidth) }; }, after);
  check('T3 after: the card is as wide as what it holds (at most 640px), its text on the fields\' text edge', card.w <= 640 && card.text === card.field && card.button[1] === 32, JSON.stringify(card));
  await page.click(after + '.ew-tool-card summary'); await page.waitForTimeout(150);
  check('T3 after: both inputs are in the details, each on its own line', (await page.locator(after + '.ew-tool-card dd').first().locator('span').allTextContents()).join('|') === '페이지 ID ← 기준 문서 확인 · 페이지 ID|표시할 문서 수 5');
  await shot('T3-side-open');
  await page.click('[data-mark-pick=off]'); await page.waitForTimeout(120);
  check('T3 option: without the mark the card drops that line; what was open stays open', !(await shown(after + '.ew-tool-card-link')) && (await shown(after + '.ew-tool-card dl')));
  await page.click('[data-mark-pick=on]'); await page.waitForTimeout(120);
  await page.click('[data-form-pick=off]'); await page.waitForTimeout(80);
  check('T3 option: the fields switch says it does not apply to a job page', (await noteText()).includes('T1, T2, T4, T5'), await noteText());
  await page.click('[data-form-pick=on]'); await page.waitForTimeout(80);
  // keyboard: the details toggle is reachable and shows focus
  await page.focus(after + '.ew-tool-card summary'); await page.keyboard.press('Tab'); await page.keyboard.press('Shift+Tab');
  const ring = await page.evaluate(s => { const c = getComputedStyle(document.querySelector(s)); return c.outlineStyle + ' ' + c.outlineWidth; }, after + '.ew-tool-card summary');
  check('T3 after: 상세 보기 shows a focus ring from the keyboard', /solid 2px/.test(ring), ring);
  await page.keyboard.press('ArrowLeft'); await page.waitForTimeout(80);
  check('an arrow key pressed inside a side does not change what is shown', (await state()).view === 'now+after');
  await page.keyboard.press('Enter'); await page.waitForTimeout(100);
  check('T3 after: Enter closes the details', !(await shown(after + '.ew-tool-card dl')));

  // ---- T4: jobs that need a hand
  await show('T4');
  check('T4 now: such a procedure opens in the summary too', (await badge()) === 'T4' && (await overview(now)) === 'true' && (await text(now.trim() + '>.mk-pane-label small')) === '열자마자 보이는 화면');
  const sumRows = await rows(now), board = await rows(after);
  check('T4 now: the summary has no mark on either job that needs a hand', sumRows.length === 4 && sumRows.every(r => !r.chip) && sumRows[2].action === '도구 연결', JSON.stringify(sumRows.map(r => [r.name, r.chip, r.action])));
  check('T4 after: four jobs, each its name and one line', board.length === 4 && board.every(r => !r.binding && r.h <= 64), JSON.stringify(board.map(r => [r.name, r.chip, r.meta, r.h])));
  check('T4 after: the job without a tool carries the mark 도구 연결 전 and the button 도구 연결', board[2].name === '변경 이력 확인' && board[2].chip === '도구 연결 전' && board[2].action === '도구 연결' && board[2].meta === META);
  check('T4 after: the job to check carries the mark 도구 확인 필요', board[3].name === '담당자 정보 조회' && board[3].chip === '도구 확인 필요' && !board[3].action && board[3].meta === META);
  const chips = await page.evaluate(s => [...document.querySelectorAll(s + '.ew-job-row .ew-author-tag[data-tool-state]')].map(e => { const c = getComputedStyle(e), n = getComputedStyle(e.parentElement); return { color: c.color, bg: c.backgroundColor, weight: c.fontWeight, radius: c.borderTopLeftRadius, gap: parseFloat(c.marginLeft), h: Math.round(e.getBoundingClientRect().height), nameWeight: n.fontWeight }; }), after);
  check('T4 after: the mark is a filled chip, not a colour of the text alone', chips.length === 2 && chips.every(c => c.bg !== 'rgba(0, 0, 0, 0)' && contrast(c.bg, 'rgb(255,255,255)') >= 1.08 && c.gap === 8 && c.radius !== '0px'), JSON.stringify(chips));
  check('T4 after: the chip text is readable on the chip', chips.every(c => contrast(c.color, c.bg) >= 4.5), chips.map(c => contrast(c.color, c.bg).toFixed(2)).join(' '));
  const place = await page.evaluate(s => { const row = document.querySelector(s + '.ew-job-row[data-job-id=history]'), a = row.querySelector('.ew-api-row-action'), b = a.getBoundingClientRect(), r = row.getBoundingClientRect(), m = row.querySelector('.ew-job-menu-button'), mb = m.getBoundingClientRect(), tag = row.querySelector('.ew-author-tag').getBoundingClientRect(); return { inRow: b.top >= r.top && b.bottom <= r.bottom, gap: Math.round(mb.left - b.right), clear: Math.round(b.left - tag.right), rowH: Math.round(r.height), h: Math.round(b.height), domBeforeMenu: !!(a.compareDocumentPosition(m) & Node.DOCUMENT_POSITION_FOLLOWING) }; }, after);
  check('T4 after: 도구 연결 sits on the job row, left of ⋯, clear of the text, 32px tall', place.inRow && place.gap >= 4 && place.gap <= 16 && place.clear > 8 && place.rowH <= 64 && place.h === 32, JSON.stringify(place));
  check('T4 after: the keyboard reaches 도구 연결 before ⋯, as the eye does', place.domBeforeMenu);
  check('T4: the jobs that need a hand are in view on the after side', (await inView(after)).slice(2).every(Boolean), JSON.stringify(await inView(after)));
  await shot('T4-side');
  await page.click(now + '.ew-procedure-menu>summary'); await page.waitForTimeout(100);
  await page.click(now + '[data-author-action=api_structure_edit]'); await page.waitForTimeout(120);
  const editRows = await rows(now);
  const nowPlace = await page.evaluate(s => { const row = document.querySelector(s + '.ew-job-row[data-job-id=history]'), b = row.querySelector('.ew-api-row-action').getBoundingClientRect(), a = row.querySelector('.ew-author-job').getBoundingClientRect(); return { below: b.top >= a.bottom - 1, tag: (row.querySelector('.ew-procedure-unconnected') || { textContent: '' }).textContent }; }, now);
  check('T4 now: after 절차 편집 the job without a tool has a grey mark and 도구 연결 on a line of its own', editRows.length === 4 && nowPlace.below && nowPlace.tag === '도구 연결 전', JSON.stringify(nowPlace));
  await shot('T4-side-now-edit');
  await page.click(after + '[data-author-action=node][data-id=history]'); await page.waitForTimeout(120);
  check('T4-1 after: the job without a tool — its page shows the same mark and one button, 도구 연결', (await badge()) === 'T4-1' && (await text(after + '.ew-tool-card-name')) === '도구 연결 전' && (await text(after + '.ew-tool-card>[data-author-action=job_api_setup]')) === '도구 연결' && (await count(after + '.ew-tool-card details')) === 0);
  const connect = await page.evaluate(s => { const b = document.querySelector(s + '.ew-tool-card>[data-author-action=job_api_setup]').getBoundingClientRect(), c = document.querySelector(s + '.ew-tool-card').getBoundingClientRect(), t = document.querySelector(s + '.ew-tool-card .ew-author-tag').getBoundingClientRect(); return { h: Math.round(b.height), right: Math.round(c.right - b.right), mid: Math.round(Math.abs((b.top + b.bottom) / 2 - (t.top + t.bottom) / 2)), cardH: Math.round(c.height) }; }, after);
  check('T4-1 after: the button is where 도구 변경 is on a connected job, the same size', connect.h === 32 && connect.right === 13 && connect.mid <= 1, JSON.stringify(connect));
  await shot('T4-1-job-unconnected');
  await page.click(after + '.ew-job-detail-header [data-author-action=node]'); await page.waitForTimeout(120);
  check('T4: back to the board, open', (await badge()) === 'T4' && (await count(after + '.ew-job-row')) === 4);
  await page.click(after + '[data-author-action=node][data-id=owner]'); await page.waitForTimeout(120);
  check('T4-2 after: the job to check — its page says so and offers 도구 변경', (await badge()) === 'T4-2' && (await text(after + '.ew-tool-card-name')) === '도구 확인 필요' && (await text(after + '.ew-tool-card-purpose')) === '연결한 도구의 현재 사용 권한을 확인해 주세요.' && (await shown(after + '.ew-tool-card>[data-author-action=job_api_setup]')) && (await count(after + '.ew-tool-card details')) === 0);
  await shot('T4-2-job-review');
  await page.click(after + '.ew-job-detail-header [data-author-action=node]'); await page.waitForTimeout(120);
  await page.click(after + '[data-author-action=list]'); await page.waitForTimeout(120);
  check('T4: the list counts the board\'s four jobs', (await page.evaluate(s => [...document.querySelectorAll(s + '[data-author-action=open]')].find(x => x.textContent.includes('Confluence')).textContent, after)).includes('작업 4'));

  // ---- T5: a procedure with people's jobs and a tool job
  await show('T5');
  const mixNow = await rows(now), mixAfter = await rows(after);
  check('T5 now: the person\'s job is two lines, the tool job has the note under it', (await badge()) === 'T5' && mixNow.length === 2 && mixNow[0].lines === 2 && mixNow[1].binding && mixNow[1].lines >= 5, JSON.stringify(mixNow.map(r => r.lines)));
  check('T5 after: both jobs are a name and one line', mixAfter.length === 2 && mixAfter.every(r => r.lines === 2 && !r.binding && !r.action && !r.chip), JSON.stringify(mixAfter));
  check('T5 after: the person\'s job reads as it does now', mixAfter[0].name === mixNow[0].name && mixAfter[0].meta === mixNow[0].meta && mixAfter[0].h === mixNow[0].h, mixAfter[0].meta);
  check('T5 after: the tool job keeps its name and the line it has now', mixAfter[1].name === '점검 기준 문서 찾기' && mixAfter[1].meta === META && mixNow[1].meta === META);
  check('T5 after: the two rows are the same height', mixAfter[0].h === mixAfter[1].h, mixAfter.map(r => r.h).join(' '));
  await shot('T5-side');
  await page.click(after + '[data-author-action=node][data-id=checks]'); await page.waitForTimeout(80);
  check('T5: a person\'s job says its page does not change and stays put', (await noteText()).includes('사람이 하는 작업') && (await state()).screen === 'proc');
  await page.click(after + '[data-author-action=node][data-id=doc]'); await page.waitForTimeout(120);
  check('T5-1 after: the tool job\'s page has the card — here the tool\'s name differs from the job\'s', (await badge()) === 'T5-1' && (await text(after + '.ew-tool-card-name')) === '기준 문서 확인사내 Confluence' && (await page.inputValue(after + 'input[name=name]')) === '점검 기준 문서 찾기');
  await page.click(after + '.ew-job-detail-header [data-author-action=node]'); await page.waitForTimeout(120);
  check('T5: back to the mixed procedure, open', (await state()).mixed && (await count(after + '.ew-job-row')) === 2);
  await page.click(now + '[data-author-action=stage_toggle][data-id=record]'); await page.waitForTimeout(80);
  check('T5: the second stage says the mock opens only the first', (await noteText()).includes('첫 단계만'));

  // ---- the 'view first' proposal
  const pair = width >= 1600 ? 'all' : 'pair';
  await show('T1', pair);
  check('view first T1: opens to read — no fields, nothing to add', (await count(view + 'input[name=overview_name]')) === 0 && (await count(view + '[data-author-action=add_stage]')) === 0 && (await count(view + '[data-author-action=start_input_add]')) === 0 && (await text(view.trim() + '>.mk-pane-label small')) === '열자마자 보이는 화면');
  const editButton = await page.evaluate(s => { const b = document.querySelector(s + '.ew-view-edit'), r = b.getBoundingClientRect(), m = document.querySelector(s + '.ew-procedure-menu>summary').getBoundingClientRect(), c = getComputedStyle(b); return { text: b.textContent, inMenu: !!b.closest('.ew-procedure-menu'), h: Math.round(r.height), gap: Math.round(m.left - r.right), mid: Math.round(Math.abs((r.top + r.bottom) / 2 - (m.top + m.bottom) / 2)), border: c.borderTopWidth, pressed: b.getAttribute('aria-pressed') }; }, view);
  check('view first T1: 편집 is a button on the title row, beside ⋯, not a menu item', editButton.text === '편집' && !editButton.inMenu && editButton.h === 32 && editButton.gap === 8 && editButton.mid <= 1 && editButton.border === '1px' && editButton.pressed === 'false', JSON.stringify(editButton));
  check('view first T1: no 절차 편집 left in the menu', (await page.locator(view + '.ew-procedure-menu button').allTextContents()).join('|') === '업무 절차 정보·분류 수정|다른 이름으로 저장|내용 확인|게시 내림');
  const listTops = { view: await listTop(view), after: await listTop(after) };
  check('view first T1: the stage list starts higher than in the straight-to-editing proposal', listTops.view < listTops.after - 150, JSON.stringify(listTops));
  await shot('T1-three');
  await page.click(view + '.ew-view-edit'); await page.waitForTimeout(120);
  check('view first: 편집 opens the editing screen on that side only', (await shown(view + 'input[name=overview_name]')) && (await shown(view + '[data-author-action=add_stage]')) && (await text(view + '.ew-view-edit')) === '편집 마침' && (await text(view.trim() + '>.mk-pane-label small')) === '‘편집’을 누른 뒤' && (await state()).viewEdit && (await shown(after + '[data-author-action=add_stage]')));
  check('view first: the keyboard stays on the button', (await focused()) === 'view/view_edit/', await focused());
  await page.click(view + '[data-author-action=stage_toggle]'); await page.waitForTimeout(120);
  await page.click(view + '[data-author-action=node][data-id=page]'); await page.waitForTimeout(120);
  check('view first: a job page is the same as in the other proposal', (await badge()) === 'T3' && (await text(view + '.ew-tool-card-name')) === (await text(after + '.ew-tool-card-name')) && (await count(view + '.ew-view-edit')) === 0);
  await page.click(view + '.ew-job-detail-header [data-author-action=node]'); await page.waitForTimeout(120);
  check('view first: back from a job one is still editing', (await shown(view + '[data-author-action=add_job]')) && (await text(view + '.ew-view-edit')) === '편집 마침');
  await page.click(view + '.ew-view-edit'); await page.waitForTimeout(120);
  check('view first: 편집 마침 returns to reading', (await count(view + '[data-author-action=add_job]')) === 0 && (await text(view + '.ew-view-edit')) === '편집' && !(await state()).viewEdit);
  await show('T2', pair);
  const readRows = await rows(view), editRows2 = await rows(after);
  check('view first T2: the rows read the same as in the other proposal', readRows.length === 2 && readRows.every((r, i) => r.name === editRows2[i].name && r.meta === editRows2[i].meta && r.lines === 2 && r.h <= 64), JSON.stringify(readRows.map(r => [r.name, r.meta, r.h])));
  check('view first T2: no ⋯ on a stage or a job, no 작업 추가, no 단계 정보 수정 while reading', (await count(view + '.ew-job-menu-button')) === 0 && (await count(view + '[data-author-action=add_job]')) === 0 && (await count(view + '[data-author-action=stage_edit]')) === 0);
  const edge = await page.evaluate(s => { const head = document.querySelector(s + '.ew-stage-toggle>img').getBoundingClientRect(), row = document.querySelector(s + '.ew-job-row .ew-author-job>img:last-child').getBoundingClientRect(), list = document.querySelector(s + '.ew-stage-list').getBoundingClientRect(); return { head: Math.round(list.right - head.right), row: Math.round(list.right - row.right) }; }, view);
  check('view first T2: the arrows of the stage and of its jobs end on one line', Math.abs(edge.head - edge.row) <= 1 && edge.row >= 8 && edge.row <= 24, JSON.stringify(edge));
  check('view first T2: the jobs are in view', (await inView(view)).every(Boolean));
  await shot('T2-three');
  await page.click(view + '[data-author-action=node][data-id=children]'); await page.waitForTimeout(120);
  await page.click(view + '.ew-job-detail-header [data-author-action=node]'); await page.waitForTimeout(120);
  check('view first: back from a job opened while reading, one is reading again', (await count(view + '[data-author-action=add_job]')) === 0 && (await count(view + '.ew-job-row')) === 2 && (await overview(now)) === 'true');
  await show('T4', pair);
  const readBoard = await rows(view);
  check('view first T4: the two marks and 도구 연결 are there while reading', readBoard.length === 4 && readBoard[2].chip === '도구 연결 전' && readBoard[2].action === '도구 연결' && readBoard[3].chip === '도구 확인 필요' && (await inView(view)).every(Boolean), JSON.stringify(readBoard.map(r => [r.name, r.chip, r.action])));
  const readPlace = await page.evaluate(s => { const row = document.querySelector(s + '.ew-job-row[data-job-id=history]'), b = row.querySelector('.ew-api-row-action').getBoundingClientRect(), r = row.getBoundingClientRect(), a = row.querySelector('.ew-author-job>img:last-child').getBoundingClientRect(), tag = row.querySelector('.ew-author-tag').getBoundingClientRect(); return { inRow: b.top >= r.top && b.bottom <= r.bottom, gap: Math.round(a.left - b.right), clear: Math.round(b.left - tag.right), h: Math.round(b.height) }; }, view);
  check('view first T4: 도구 연결 sits on its row, left of the arrow, clear of the text', readPlace.inRow && readPlace.gap >= 6 && readPlace.gap <= 16 && readPlace.clear > 8 && readPlace.h === 32, JSON.stringify(readPlace));
  await shot('T4-three');
  await show('T5', pair);
  const readMixed = await rows(view), nowMixed = await rows(now);
  check('view first T5: a procedure with people\'s jobs also opens to read (today it opens in the editing screen)', (await count(view + 'input[name=overview_name]')) === 0 && (await count(view + '[data-author-action=add_stage]')) === 0 && (await count(now + '[data-author-action=add_stage]')) === 1 && readMixed.length === 2);
  check('view first T5: the person\'s job reads as it does now; the two rows are the same height but for the last one\'s missing line', readMixed[0].name === nowMixed[0].name && readMixed[0].meta === nowMixed[0].meta && Math.abs(readMixed[0].h - readMixed[1].h) <= 1, JSON.stringify(readMixed.map(r => [r.name, r.meta, r.h])));
  await shot('T5-three');
  for (const scene of ['T1', 'T2', 'T3', 'T4', 'T5']) {
    await show(scene, pair);
    const over = await page.evaluate(() => [...document.querySelectorAll('.mk-pane[data-shown=true]')].map(p => { const s = p.querySelector('.ew-author-scroll') || p.querySelector('#ees-work-panel'); return s.scrollWidth - s.clientWidth; }));
    check(`${scene} (${pair}): no sideways scroll on any side shown`, over.every(v => v <= 0), JSON.stringify(over));
    const cut = await page.evaluate(() => [...document.querySelectorAll('.mk-pane[data-side=view] :is(.ew-job-row-label>span,.ew-job-meta,.ew-view-edit,.ew-api-row-action,.ew-author-tag,h2,.ew-stage-name)')].filter(e => e.getBoundingClientRect().width > 0 && (e.scrollWidth > e.clientWidth + 1)).map(e => e.textContent.trim().slice(0, 20)));
    check(`${scene} (${pair}): no cut text on the view-first side`, cut.length === 0, JSON.stringify(cut));
  }
  // which sides are shown
  await show('T2', 'all');
  await page.click('[data-pane-pick=now]'); await page.waitForTimeout(100);
  check('sides: 지금 can be turned off, leaving the two proposals side by side', (await state()).view === 'after+view' && !(await shown(now + '#ees-work-panel')) && (await shown(after + '#ees-work-panel')) && (await shown(view + '#ees-work-panel')));
  await page.click('[data-pane-pick=after]'); await page.waitForTimeout(100);
  check('sides: one side alone shows the whole window, with its left menu', (await state()).view === 'view' && (await shown(view + '.fu-side')));
  await page.click('[data-pane-pick=view]'); await page.waitForTimeout(100);
  check('sides: the last one stays on', (await state()).view === 'view' && (await noteText()).includes('하나는'));
  await page.evaluate(() => document.activeElement && document.activeElement.blur());
  await page.keyboard.press('ArrowLeft'); await page.waitForTimeout(100);
  check('sides: ← goes to the side before', (await state()).view === 'after');
  await shot('T2-after-alone');

  // ---- things the mock does not do say so; where one had scrolled to is kept
  await show('T2');
  await page.click(after + '[data-author-action=add_job]'); await page.waitForTimeout(80);
  check('a press the mock does not act on says it works as the product does', (await noteText()).includes('지금 제품과 같은 동작') && (await state()).screen === 'proc');
  const noteBox = await page.evaluate(() => { const n = document.querySelector('#mock-note').getBoundingClientRect(), l = [...document.querySelectorAll('.mk-pane-label')].map(e => e.getBoundingClientRect().bottom); return { top: Math.round(n.top), labels: Math.round(Math.max(...l)), bottom: Math.round(innerHeight - n.bottom) }; });
  check('the note sits at the bottom, clear of the side headings', noteBox.top > noteBox.labels + 100 && noteBox.bottom >= 60, JSON.stringify(noteBox));
  await show('T4');   // the longest of the screens, so there is something to scroll at either window size
  const scrolled = await page.evaluate(s => { const e = document.querySelector(s + '.ew-author-scroll'); e.scrollTop = 60; return e.scrollTop; }, after);
  await page.click('[data-mark-pick=off]'); await page.waitForTimeout(120);
  const kept = await page.evaluate(s => document.querySelector(s + '.ew-author-scroll').scrollTop, after);
  check('a switch above redraws the side without losing where one had scrolled to', scrolled > 0 && kept === scrolled, scrolled + ' → ' + kept);
  await page.click('[data-mark-pick=on]');

  // ---- nothing runs off the side; text is not cut
  for (const scene of ['T1', 'T2', 'T3', 'T4', 'T5']) for (const form of ['on', 'off']) {
    await show(scene, 'side', 'on', form);
    if (scene === 'T3') await page.evaluate(() => document.querySelectorAll('.mk-pane[data-side=after] .ew-tool-card details').forEach(d => { d.open = true; }));
    const over = await page.evaluate(() => [...document.querySelectorAll('.mk-pane')].map(p => { const s = p.querySelector('.ew-author-scroll') || p.querySelector('#ees-work-panel'); return s.scrollWidth - s.clientWidth; }));
    check(`${scene} (fields ${form}): no sideways scroll in either side`, over.every(v => v <= 0), JSON.stringify(over));
    const cut = await page.evaluate(() => [...document.querySelectorAll('.mk-pane[data-side=after] :is(.ew-job-row-label>span,.ew-job-meta,.ew-tool-card-name,.ew-tool-card-purpose,.ew-tool-card-link,.ew-tool-card dd,.ew-api-row-action,.ew-tool-card button,.ew-author-tag)')].filter(e => e.getBoundingClientRect().width > 0 && (e.scrollWidth > e.clientWidth + 1)).map(e => e.textContent.trim().slice(0, 20)));
    check(`${scene} (fields ${form}): no cut text on the after side`, cut.length === 0, JSON.stringify(cut));
  }
  // ---- one side at a time shows the whole window (menu, chat)
  await show('T2', 'after');
  check('single view: only the after side, with its left menu', (await shown(after + '.fu-side')) && !(await shown('.mk-pane[data-side=now]')));
  if (width >= 1200) check('single view: the chat shows from 1200', await shown(after + '.fu-chat'));
  await shot('T2-after');
  await page.evaluate(() => document.activeElement && document.activeElement.blur());
  await page.keyboard.press('ArrowLeft'); await page.waitForTimeout(100);
  check('single view: ← shows now', (await state()).view === 'now' && (await shown('.mk-pane[data-side=now] .fu-side')));
  await page.click('[data-mark-pick=off]'); await page.waitForTimeout(80);
  check('single view: a switch that only touches the proposals says so when only now is shown', (await noteText()).includes('바꾼 두 쪽'), await noteText());
  await page.click('[data-mark-pick=on]');
  await page.keyboard.press('5'); await page.waitForTimeout(100);
  check('keys 1–5 pick the screen', (await state()).where === 'T5');
  // ---- the guide: the reference line and folding
  await show('T2');
  check('the reference line is closed until asked for', !(await page.locator('#mock-step-text').textContent()).includes('참고'));
  await page.click('#mock-ref-toggle'); await page.waitForTimeout(80);
  check('참고 opens the reference line, which also says the keys', (await page.locator('#mock-step-text').textContent()).includes('main 598440d') && (await page.locator('#mock-step-text').textContent()).includes('숫자 키 1~5'));
  await page.click('#mock-ref-toggle');
  await page.click('#mock-fold'); await page.waitForTimeout(80);
  check('the explanation folds; the badge and the buttons stay', (await shown('#mock-badge')) && (await shown('[data-step=T1]')) && !(await shown('#mock-step-text')) && !(await shown('#mock-ref-toggle')));
  await page.click('#mock-fold');
  check('no page errors', errors.length === 0, JSON.stringify(errors));
  await page.close();
}

(async () => {
  const browser = await chromium.launch();
  await run(browser, 1920, 1080); await run(browser, 1366, 768);
  await browser.close();
  const failed = results.filter(r => !r.ok);
  fs.writeFileSync(reportPath, JSON.stringify({ mock: path.basename(file), checks: results.length, passed: results.length - failed.length, failed: failed.length, results }, null, 1));
  console.log(`checks ${results.length} passed ${results.length - failed.length} failed ${failed.length}`);
  for (const r of failed) console.log('FAIL', r.size, r.name, r.detail);
})();
