/* scripts/figma_check.js runs inside Figma (use_figma). These checks feed it a small
 * in-memory file with the same API surface it reads; real-file runs are recorded in evals. */
const test = require('node:test'), assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path');
const code = fs.readFileSync(path.join(__dirname, '..', 'scripts', 'figma_check.js'), 'utf8');
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const KEY = 'XK2wTos6sEuxSHhIj7cqg6';

function segments(text, links) {
  const out = [];
  let at = 0;
  for (const link of [...links].sort((a, b) => a.start - b.start)) {
    if (link.start > at) out.push({ start: at, end: link.start, hyperlink: null });
    out.push({ start: link.start, end: link.end, hyperlink: link.hyperlink });
    at = link.end;
  }
  if (at < text.length) out.push({ start: at, end: text.length, hyperlink: null });
  return out;
}
const text = (id, characters, links = []) => ({ id, type: 'TEXT', characters, links });
const link = (characters, label, hyperlink) => {
  const start = characters.indexOf(label);
  return { start, end: start + label.length, hyperlink };
};
const node = (id, target) => ({ type: 'NODE', value: target });

function file(pages) {
  const nodes = new Map();
  let auto = 0;
  const build = (spec, parent) => {
    const made = { id: spec.id || 'x:' + ++auto, name: spec.name || spec.type, type: spec.type, parent };
    if (spec.type === 'TEXT') {
      made.characters = spec.characters;
      made.getStyledTextSegments = () => segments(made.characters, spec.links);
    } else made.children = (spec.children || []).map((child) => build(child, made));
    nodes.set(made.id, made);
    return made;
  };
  const root = { type: 'DOCUMENT' };
  root.children = pages.map((page) => build({ ...page, type: 'PAGE' }, root));
  const calls = [];
  return { calls, figma: { root, fileKey: KEY,
    getNodeByIdAsync: async (id) => nodes.get(id) || null,
    setCurrentPageAsync: async (page) => { calls.push(page.name); } } };
}

function base(overrides = {}) {
  const mapText = '공통 · 화면 틀·이동 / 워크 · 도구';
  const archiveLine = '지난 기록은 91 · 보관 ‘지난 변경 기록’에 있습니다 →';
  return [
    { id: '897:760', name: '00 · 설계 관리 · 먼저 읽기', children: [
      { id: '1288:2', type: 'FRAME', name: '기능 지도', children: [text('1288:12', mapText, [
        link(mapText, '공통 · 화면 틀·이동', node('', '1284:3046')), link(mapText, '워크 · 도구', node('', '1285:1841'))])] },
      { id: '898:31', type: 'FRAME', name: '변경 기록', children: overrides.log || [
        text('898:32', '변경 기록'),
        text('a:1', archiveLine, [link(archiveLine, '지난 변경 기록', node('', 'r:list'))]),
        text('a:2', 'C130 · 2026-10-29 · 고정 점검 도입 · PR #106 · 백업 없음'),
        text('a:3', 'C131 · 2026-10-30 · 화면 수정 · PR #107 · 백업 B066')] }] },
    { id: '1284:3046', name: overrides.featureName || '공통 · 화면 틀·이동', children: [
      { id: 'h:1', type: 'FRAME', name: 'Header · 공통 · 화면 틀·이동', children: overrides.header || [text('h:2', '최신판 3판 · 공통 기준')] },
      ...(overrides.feature || [])] },
    { id: '1285:1841', name: '워크 · 도구', children: [{ id: 'f:1', type: 'FRAME', name: 'B10-1 · 도구 목록', children: [
      text('f:2', 'C66에서 작업실 → 공통-3으로 옮김')] }] },
    { id: '897:761', name: '70 · 작업실 · 실험·검토', children: [text('w:1', '작업실 사용 안내')] },
    { id: '1722:1395', name: '91 · 보관 · 기능 페이지 이전 판과 옛 설계', children: [
      { id: 'r:list', type: 'FRAME', name: '지난 변경 기록 · 목록', children: [
        text('r:1', 'C01  |  2026-10-01  |  Claude  |  공통-1 화면 정리'),
        text('r:2', 'C118 · 2026-10-28 KST · 워크-2 이전 화면을 보관으로 (백업 B056)'),
        text('r:3', 'C129 · 결과 확인 직접 표시')] },
      { id: 'old:1', type: 'FRAME', name: 'PREVIOUS · B5 · 옛 도구 화면', children: [] }] },
    { id: 'b:56', name: overrides.backupName || '99 · 백업 · B056 · 2026-10-28 · 도구 이전 화면 보관 전', children: [] },
    { id: 'b:66', name: '99 · 백업 · B066 · 2026-10-30 · 화면 수정 전', children: [] },
  ];
}
async function check(pages) {
  const made = file(pages);
  const result = await new AsyncFunction('figma', code)(made.figma);
  return { result, calls: made.calls };
}

test('a file that follows the naming, log, link and backup rules passes and reports the next number', async () => {
  const { result, calls } = await check(base());
  assert.deepEqual(result.errors, []);
  assert.equal(result.ok, true);
  assert.equal(result.next, 'C132');
  assert.equal(result.logLines, 2);
  assert.deepEqual(result.backups, [['B056', '2026-10-28', 'C118', 'PR 확인 필요'], ['B066', '2026-10-30', 'C131', 'PR #107']]);
  assert.ok(!calls.some((name) => name.startsWith('99 · ')), 'backup pages are not opened');
  assert.equal(calls[calls.length - 1], '00 · 설계 관리 · 먼저 읽기');
});

test('numbered or status page names and backup names without “무엇 고치기 전” are errors', async () => {
  const { result } = await check(base({ featureName: '공통-1 · 화면 틀·이동 · 초안', backupName: 'B056 · 도구 이전 화면 · 2026-10-28' }));
  assert.equal(result.ok, false);
  assert.ok(result.errors.some((e) => e.startsWith('이름: 공통-1')));
  assert.ok(result.errors.some((e) => e.startsWith('백업 이름: B056')));
});

test('old page names in current guides are errors, history sentences and archives are not', async () => {
  const { result } = await check(base({ feature: [text('g:1', '권한별 메뉴는 공통-1 R7에서 정합니다.'), text('g:2', '단계는 페이지 이름 끝에만 적습니다.')] }));
  const old = result.errors.filter((e) => e.startsWith('옛 표기'));
  assert.equal(old.length, 2);
  assert.ok(old[0].includes('g:1') || old[1].includes('g:1'));
  assert.ok(!result.errors.some((e) => e.includes('f:2') || e.includes('r:1')));
});

test('missing link targets are errors and latest-looking links into archives are warnings', async () => {
  const header = '최신 화면 → · 이전 기준 →';
  const { result } = await check(base({ header: [text('h:2', header, [
    link(header, '최신 화면', node('', 'old:1')), link(header, '이전 기준', node('', 'old:1'))]),
    text('h:3', '없는 화면 →', [{ start: 0, end: 5, hyperlink: { type: 'URL', value: 'https://www.figma.com/design/' + KEY + '?node-id=9-99' } }])] }));
  assert.ok(result.errors.some((e) => e.startsWith('없는 노드 링크: h:3 → 9:99')));
  const archived = result.warnings.filter((w) => w.startsWith('보관을 가리키는 링크'));
  assert.equal(archived.length, 1);
  assert.ok(archived[0].includes('최신 화면'));
});

test('the 00 log must stay one line per change, at most 20 lines, numbered after the archive', async () => {
  const many = Array.from({ length: 21 }, (_, i) => text('l:' + i, 'C' + (130 + i) + ' · 2026-10-29 · 변경 ' + i + ' · PR 없음 · 백업 없음'));
  let { result } = await check(base({ log: many }));
  assert.ok(result.errors.some((e) => e.startsWith('00 변경 기록 21줄 > 20')));
  ({ result } = await check(base({ log: [
    text('l:a', 'C130 · 2026-10-29 · 여러 줄 기록\n자세한 내용 · PR #106 · 백업 없음'),
    text('l:b', 'C120 · 2026-10-29 · 번호를 잘못 셈 · PR 없음 · 백업 없음'),
    text('l:c', 'C131 · 2026-10-29 · PR 칸 없음')] })));
  assert.ok(result.errors.some((e) => e.startsWith('한 줄 형식 아님: C130')));
  assert.ok(result.errors.some((e) => e.includes('C129보다 작음: C120')));
  assert.ok(result.errors.some((e) => e.startsWith('한 줄 형식 아님: C131')));
});

test('size limits: a heavy feature page is a cleanup warning, a heavy 00 page is an error', async () => {
  const heavy = Array.from({ length: 10001 }, (_, i) => ({ id: 'n:' + i, type: 'FRAME', name: 'n', children: [] }));
  const long = text('t:long', '가'.repeat(20001));
  const pages = base({ feature: heavy });
  pages[0].children.push(long);
  const { result } = await check(pages);
  assert.ok(result.warnings.some((w) => w.startsWith('정리 신호: 공통 · 화면 틀·이동 요소 1')));
  assert.ok(result.errors.some((e) => e.startsWith('00 글자 ')));
});

test('previous-version frames left on feature pages and pages missing from the function map are warnings', async () => {
  const pages = base({ feature: [{ id: 'p:1', type: 'FRAME', name: 'PREVIOUS20 · 업무 목업', children: [] }] });
  pages.splice(2, 0, { id: 'new:1', name: '워크 · 빠른 문장', children: [] });
  const { result } = await check(pages);
  assert.ok(result.warnings.some((w) => w.startsWith('이전 판으로 보이는 이름: 공통 · 화면 틀·이동 / PREVIOUS20')));
  assert.ok(result.warnings.some((w) => w === '기능 지도에 없는 기능 페이지: 워크 · 빠른 문장'));
});
