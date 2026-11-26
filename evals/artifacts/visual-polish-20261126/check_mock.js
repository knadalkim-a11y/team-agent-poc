// Scripted browser checks of design mock 22 (visual polish, now / after) at two window sizes.
// usage: node evals/artifacts/visual-polish-20261126/check_mock.js docs/mockups/ees-work/design-mock-22-visual-polish.html [report.json]
const { chromium } = require('playwright'); const path = require('path'); const fs = require('fs');
(async () => {
  const [file, outFile] = process.argv.slice(2);
  const browser = await chromium.launch(); const results = []; const errors = []; const outside = [];
  const check = (size, name, ok, detail = '') => results.push({ size, name, ok: !!ok, detail: String(detail) });
  const on = '.mk-pane[data-polish="on"] ', off = '.mk-pane[data-polish="off"] ';
  for (const [width, height] of [[1920, 1080], [1366, 768]]) {
    const size = width + 'x' + height;
    const page = await browser.newPage({ viewport: { width, height } });
    page.on('pageerror', e => errors.push(size + ' ' + e)); page.on('console', m => { if (m.type() === 'error') errors.push(size + ' ' + m.text()); });
    page.on('request', r => { if (!/^(file|data|blob|about):/.test(r.url())) outside.push(r.url()); });
    await page.goto('file://' + path.resolve(file)); await page.evaluate(() => document.fonts.ready);
    const show = (scene, view) => page.evaluate(([s, v]) => window.mockShow(s, v), [scene, view]);
    const vis = sel => page.evaluate(s => { const e = document.querySelector(s); if (!e) return false; const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== 'hidden'; }, sel);
    const rect = sel => page.evaluate(s => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect(); return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), r: Math.round(r.right), b: Math.round(r.bottom) }; }, sel);
    const rects = sel => page.evaluate(s => [...document.querySelectorAll(s)].map(e => { const r = e.getBoundingClientRect(); return [Math.round(r.x), Math.round(r.right)]; }), sel);
    const textX = sel => page.evaluate(s => [...document.querySelectorAll(s)].map(e => { const g = document.createRange(); g.selectNodeContents(e); return Math.round(g.getBoundingClientRect().x); }), sel);
    const style = (sel, prop, pseudo) => page.evaluate(([s, p, q]) => { const e = document.querySelector(s); return e ? getComputedStyle(e, q || null).getPropertyValue(p).trim() : null; }, [sel, prop, pseudo]);
    const same = list => list.length > 0 && list.every(v => JSON.stringify(v) === JSON.stringify(list[0]));

    // --- the frame of the mock
    check(size, 'opens on P1, side by side', (await page.textContent('#mock-badge')) === '시안 1 · 저장·실행 안 됨 · P1' && await page.getAttribute('#mock-stage', 'data-view') === 'side');
    for (const scene of ['P1', 'P2', 'P3', 'P4']) {
      for (const view of ['side', 'now', 'after']) {
        await show(scene, view); await page.waitForTimeout(50);
        const a = await vis(on + '.fu-main'), b = await vis(off + '.fu-main');
        check(size, `${scene} ${view}: the right version is shown`, view === 'side' ? a && b : view === 'now' ? b && !a : a && !b);
        check(size, `${scene} ${view}: badge says mock and the screen number`, (await page.textContent('#mock-badge')) === '시안 1 · 저장·실행 안 됨 · ' + scene);
        check(size, `${scene} ${view}: no sideways page scroll`, await page.evaluate(() => document.scrollingElement.scrollWidth <= window.innerWidth));
        if (view === 'side') check(size, `${scene} side: left menu and chat are hidden`, !(await vis(on + '.fu-side')) && !(await vis(off + '.fu-chat')));
      }
      await show(scene, 'side');
      check(size, `${scene}: now keeps the product values`, await style(off + '#ees-work-panel', '--ees-text-primary') === '#1d2128' && await style(off + '#ees-work-panel', '--ees-text-tertiary') === await style(off + '#ees-work-panel', '--ees-text-secondary'));
      check(size, `${scene}: after takes the new values, three text levels`, await style(on + '#ees-work-panel', '--ees-text-primary') === '#171b22' && await style(on + '#ees-work-panel', '--ees-text-secondary') === '#414959' && await style(on + '#ees-work-panel', '--ees-text-tertiary') === '#5e6573');
      // what is really on the after side: five type sizes, four corner values
      await show(scene, 'after');
      const seen = await page.evaluate(() => { const sizes = new Set(), radii = new Set();
        for (const root of document.querySelectorAll('.mk-pane[data-polish="on"] :is(#ees-work-panel,#ees-work-entry)')) for (const e of root.querySelectorAll('*')) {
          if (e.closest('details:not([open])>:not(summary)')) continue;
          const r = e.getBoundingClientRect(); if (!r.width || !r.height) continue; const c = getComputedStyle(e);
          if ([...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()) || /^(INPUT|SELECT|TEXTAREA)$/.test(e.tagName)) sizes.add(c.fontSize + '/' + c.lineHeight);
          if (c.borderTopLeftRadius !== '0px' && (c.borderTopWidth !== '0px' || c.backgroundColor !== 'rgba(0, 0, 0, 0)' || c.boxShadow !== 'none')) radii.add(c.borderTopLeftRadius);
        } return { sizes: [...sizes].sort(), radii: [...radii].sort() }; });
      check(size, `${scene} after: only the five type steps`, seen.sizes.every(s => ['24px/32px', '16px/24px', '14px/22px', '13px/20px', '12px/18px'].includes(s)), seen.sizes.join(' '));
      check(size, `${scene} after: only the four corner values`, seen.radii.every(r => ['8px', '12px', '5px', '999px', '50%'].includes(r)), seen.radii.join(' '));
    }

    // --- P1 after
    await show('P1', 'after');
    check(size, 'P1 after: title 24, stage name 14, field label 13', await style(on + '.ew-author-definition-head h2', 'font-size') === '24px' && await style(on + '.ew-stage-name', 'font-size') === '14px' && await style(on + '.ew-procedure-info label', 'font-size') === '13px');
    check(size, 'P1 after: one-line fields are 40px high', (await rect(on + 'input[name=overview_name]')).h === 40 && (await rect(on + '.ew-procedure-info select')).h === 40);
    check(size, 'P1 after: name field is not stretched', (await rect(on + 'input[name=overview_name]')).w <= 344);
    check(size, 'P1 after: no box around the three fields', await style(on + '.ew-procedure-info', 'border-top-width') === '0px');
    check(size, 'P1 after: the quiet text levels reach the centre', await style(on + '.ew-job-meta', 'color') === 'rgb(94, 101, 115)' && await style(on + '.ew-stage-count', 'color') === 'rgb(65, 73, 89)');
    const list = await rect(on + '.ew-stage-list'), last = await rect(on + '#ees-work-designer>footer>button:last-child');
    check(size, 'P1 after: bottom buttons end where the list ends', Math.abs(list.r - last.r) <= 1, list.r + ' vs ' + last.r);
    const dots = [...await rects(on + '.ew-stage-menu-button'), ...await rects(on + '.ew-job-row>.ew-job-menu-button')], arrows = [...await rects(on + '.ew-stage-toggle>img'), ...await rects(on + '.ew-author-job>img')];
    check(size, 'P1 after: dots share one column on stage and job rows', dots.length >= 3 && same(dots), JSON.stringify(dots));
    check(size, 'P1 after: arrows share one column on stage and job rows', arrows.length >= 4 && same(arrows), JSON.stringify(arrows));
    check(size, 'P1 after: counts end at the same place on every stage', same((await rects(on + '.ew-stage-count')).map(r => r[1])));
    const edges = [...await textX(on + '.ew-stage-name'), ...await textX(on + '.ew-stage-description p'), ...await textX(on + '.ew-job-row-label>span'), ...(await rects(on + '.ew-api-job-binding')).map(r => r[0]), ...(await rects(on + '[data-author-action=add_job]')).map(r => r[0] + 8)];
    check(size, 'P1 after: one left edge inside a stage', same(edges), JSON.stringify(edges));
    const note = await rect(on + '.ew-api-job-binding'), act = await rect(on + '.ew-api-row-action');
    check(size, "P1 after: '도구 변경' sits inside the tool note", act.x > note.x && act.r < note.r && act.y > note.y && act.b < note.b);
    const noteText = await page.evaluate(s => Math.max(...[...document.querySelectorAll(s + '.ew-api-job-binding>*')].map(e => { const r = document.createRange(); r.selectNodeContents(e); return r.getBoundingClientRect().right; })), on);
    check(size, "P1 after: note text does not run under '도구 변경'", noteText < act.x, Math.round(noteText) + ' < ' + act.x);
    check(size, 'P1 after: saved lamp is drawn', await style(on + '#ees-work-designer>footer>small', 'width', '::before') === '6px');
    check(size, 'P1 after: 저장·게시 are off (nothing to save) and still readable', await page.evaluate(s => [...document.querySelectorAll(s + '#ees-work-designer>footer>button')].every(b => b.disabled && getComputedStyle(b).opacity === '1' && getComputedStyle(b).color === 'rgb(140, 148, 163)'), on));
    check(size, 'P1 after: the tab mark is 2px and inside the strip', await style(on + '.ew-author-tabs>button[aria-selected=true]', 'height', '::after') === '2px' && await style(on + '.ew-author-tabs>button[aria-selected=true]', 'bottom', '::after') === '0px' && await page.evaluate(s => { const n = document.querySelector(s + '.ew-author-tabs'); return n.scrollHeight <= n.clientHeight; }, on));
    check(size, 'P1 after: the page menu is an outlined 32px button', (await rect(on + '.ew-procedure-menu>summary')).w === 32 && await style(on + '.ew-procedure-menu>summary', 'border-top-width') === '1px');
    // keyboard focus: one mark, never cut off
    const ring = async sel => { await page.focus(sel); await page.keyboard.press('Shift+Tab'); await page.keyboard.press('Tab'); await page.waitForTimeout(250); return page.evaluate(() => { const c = getComputedStyle(document.activeElement); return [c.outlineStyle, c.outlineWidth, c.outlineColor, c.outlineOffset].join(' '); }); };
    check(size, 'P1 after: focus on a link is the 2px accent line', await ring(on + '[data-author-action=add_job]') === 'solid 2px rgb(43, 95, 168) 2px');
    check(size, 'P1 after: focus on a tab is drawn inside the strip', await ring(on + '.ew-author-tabs>button[aria-selected=true]') === 'solid 2px rgb(43, 95, 168) -2px');
    check(size, 'P1 after: focus on a stage row is drawn inside the list', await ring(on + '.ew-stage-toggle') === 'solid 2px rgb(43, 95, 168) -2px');
    check(size, 'P1 after: focus on a field is the same line on its border', await ring(on + 'input[name=overview_name]') === 'solid 2px rgb(43, 95, 168) -1px');
    if (width >= 1440) check(size, 'P1 after: focus on 공장 is drawn', await ring(on + '#ees-work-site-trigger') === 'solid 2px rgb(43, 95, 168) -2px' && await style(on + '.ew-scope', 'overflow-x') === 'visible');
    // heights
    const tall = {}; for (const view of ['now', 'after']) { await show('P1', view); tall[view] = await page.evaluate(p => document.querySelector(p + '.ew-author-scroll').scrollHeight, view === 'now' ? off : on); }
    check(size, 'P1: after is at most 3% taller than now', tall.after <= tall.now * 1.03, `${tall.now} -> ${tall.after}`);

    // --- P2 after
    await show('P2', 'after');
    const xs = [...(await textX(on + '.ew-vd-name')).slice(0, 1), (await rect(on + '.ew-vd-checks .ew-vd-check-done')).x, (await rect(on + '.ew-vd-checks li:not([data-done=true]) input[type=checkbox]')).x, ...await textX(on + '.ew-vd-tool-detail h4'), ...await textX(on + '.ew-vd-more .ew-text')];
    check(size, 'P2 after: name, check boxes, 입력 and 자세히 share one left edge', same(xs), JSON.stringify(xs));
    check(size, 'P2 after: that edge is the one P1 uses for a stage name', xs[0] - (await rect(on + '.ew-center-task-list')).x === 53);
    check(size, 'P2 after: the job in hand is tinted, its number in the accent', await style(on + '.ew-vd-entry[data-expanded=true]>.ew-vd-item', 'background-color') === 'rgb(237, 242, 250)' && await style(on + '.ew-vd-entry[data-expanded=true] .ew-center-task-number', 'background-color') === 'rgb(43, 95, 168)');
    check(size, 'P2 after: numbers are 24px circles', await page.evaluate(s => [...document.querySelectorAll(s + '.ew-center-task-number')].every(e => { const r = e.getBoundingClientRect(); return Math.round(r.width) === 24 && Math.round(r.height) === 24; }), on));
    check(size, 'P2 after: one solid action, 지금 실행', await page.evaluate(s => [...document.querySelectorAll(s + '#ees-work-panel button')].filter(b => getComputedStyle(b).backgroundColor === 'rgb(23, 27, 34)').map(b => b.textContent.trim()).join('|'), on) === '지금 실행');
    const run = await rect(on + '.ew-vd-run');
    check(size, 'P2 after: 실행 is an outlined 32px button, no narrower than now', run.h === 32 && run.w >= 106 && await style(on + '.ew-vd-run', 'border-top-width') === '1px', JSON.stringify(run));
    check(size, 'P2 after: an empty check box has a 3:1 line', await style(on + '.ew-vd-checks input[type=checkbox]', 'border-top-color') === 'rgb(138, 146, 162)');
    const rows = await page.evaluate(s => [...document.querySelectorAll(s + '.ew-center-task-row')].map(r => { const b = r.getBoundingClientRect(); return [Math.round(b.y), Math.round(b.bottom)]; }), on);
    check(size, 'P2 after: rows touch, so the rail does not break', rows.length >= 2 && rows.slice(1).every((r, i) => Math.abs(r[0] - rows[i][1]) <= 1), JSON.stringify(rows));
    check(size, 'P2 after: the tab mark is 2px and inside the strip', await style(on + '.ew-tabs>button[aria-pressed=true]', 'height', '::after') === '2px' && await page.evaluate(s => { const n = document.querySelector(s + '.ew-tabs'); return n.scrollHeight <= n.clientHeight; }, on));
    const tall2 = {}; for (const view of ['now', 'after']) { await show('P2', view); tall2[view] = await page.evaluate(p => Math.round(document.querySelector(p + '.ew-center-task-list').getBoundingClientRect().height), view === 'now' ? off : on); }
    check(size, 'P2: the job list is at most 3% taller than now', tall2.after <= tall2.now * 1.03, `${tall2.now} -> ${tall2.after}`);
    // the page head keeps one rhythm on both screens
    const head = {}; for (const [scene, t, tabs, first] of [['P1', '.ew-author-definition-head h2', '.ew-author-tabs', '.ew-procedure-info'], ['P2', '.ew-vd-title h2', '.ew-tabs', '.ew-center-task-heading']]) { await show(scene, 'after'); const top = (await rect(on + '#ees-work-panel')).y; head[scene] = [(await rect(on + t)).y - top, (await rect(on + tabs)).y - top, (await rect(on + first)).y - top]; }
    check(size, 'after: title, tabs and first content sit at the same height in the panel on P1 and P2', same([head.P1, head.P2]), JSON.stringify(head));

    // --- P3 (values only) and P4 (with the list)
    await show('P3', 'side');
    check(size, 'P3: both sides say the same words', (await page.textContent(off + '#ees-work-content')).trim() === (await page.textContent(on + '#ees-work-content')).trim() && (await page.textContent(on + '#ees-work-content')).includes('업무 절차를 선택해 주세요'));
    check(size, 'P3 after: the notice is on the scale (16 and 13)', await style(on + '.ew-empty h3', 'font-size') === '16px' && await style(on + '.ew-empty p', 'font-size') === '13px');
    await show('P4', 'side');
    check(size, 'P4 now: the product notice', (await page.textContent(off + '#ees-work-content')).includes('업무 절차를 선택해 주세요'));
    check(size, 'P4 after: two pieces of work, each with 시작', await page.evaluate(s => document.querySelectorAll(s + '.ew-home-row').length === 2 && [...document.querySelectorAll(s + '.ew-home-row button')].every(b => b.textContent.trim() === '시작'), on));
    check(size, 'P4 after: no solid button', await page.evaluate(s => [...document.querySelectorAll(s + '#ees-work-panel button')].every(b => getComputedStyle(b).backgroundColor !== 'rgb(23, 27, 34)'), on));
    check(size, 'P4 after: 새 업무 절차 starts on the list edge and hugs its words', (await rect(on + '.ew-home-new')).x + 8 === (await rect(on + '.ew-home-list')).x && (await rect(on + '.ew-home-new')).w < 140);

    // --- a mock shows: nothing in a pane does anything
    await show('P1', 'after');
    const before = await page.evaluate(s => document.querySelector(s + '#ees-work-panel').innerHTML.length, on);
    await page.click(on + '[data-author-action=add_job]'); await page.click(on + '.ew-stage-toggle'); await page.click(on + '.ew-procedure-menu>summary');
    check(size, 'P1: pressing things changes nothing and the menu stays shut', before === await page.evaluate(s => document.querySelector(s + '#ees-work-panel').innerHTML.length, on) && !(await page.evaluate(s => document.querySelector(s + '.ew-procedure-menu').open, on)) && page.url().startsWith('file:'));
    await show('P2', 'after'); await page.click(on + '.ew-vd-checks li:not([data-done=true]) label');
    check(size, 'P2: a check box does not tick', !(await page.evaluate(s => document.querySelector(s + '.ew-vd-checks input[type=checkbox]').checked, on)));

    // --- guide strip
    await page.click('#mock-badge');
    for (const key of ['2', '3', '4', '1']) { await page.keyboard.press(key); check(size, `key ${key} shows P${key}`, (await page.textContent('#mock-badge')).endsWith('P' + key)); }
    await page.keyboard.press('ArrowLeft'); check(size, '← shows now', await page.getAttribute('#mock-stage', 'data-view') === 'now');
    await page.keyboard.press('ArrowRight'); check(size, '→ shows after', await page.getAttribute('#mock-stage', 'data-view') === 'after');
    const stageBefore = (await rect('#mock-stage')).h; await page.click('#mock-words-toggle');
    check(size, 'values table opens over the screen without pushing it', await vis('#mock-words') && (await page.textContent('#mock-words')).includes('5단계') && (await rect('#mock-stage')).h === stageBefore);
    await page.click('#mock-words-toggle'); await page.click('#mock-fold');
    check(size, 'guide folds', await page.getAttribute('#mock-guide', 'data-collapsed') === 'true');
    await show('P1', 'after');
    if (width < 1440) check(size, 'under 1440 the left menu is a rail', (await rect(on + '.fu-side')).w === 56 && await page.getAttribute(on + '.fu-side', 'data-compact') === 'true');
    else check(size, 'at 1920 the left menu is open', (await rect(on + '.fu-side')).w === 256);
    await page.close();
  }
  check('all', 'no page errors', errors.length === 0, errors.join(' | '));
  check('all', 'no request leaves the file', outside.length === 0, outside.join(' | '));
  const failed = results.filter(r => !r.ok);
  for (const r of failed) console.log('FAIL', r.size, r.name, r.detail);
  console.log(`checks ${results.length} passed ${results.length - failed.length} failed ${failed.length}`);
  if (outFile) fs.writeFileSync(outFile, JSON.stringify({ file, checks: results.length, failed: failed.length, results }, null, 1) + '\n');
  await browser.close(); process.exit(failed.length ? 1 : 0);
})();
