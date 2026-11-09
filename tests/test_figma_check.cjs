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
  const entries = [
    ['공통 · 화면 틀', '1288:11', '1284:3047', '1284:3046'], ['업무 · 운영', '1288:42', '1284:3107', '1284:3106'],
    ['워크 · 업무 절차', '1288:63', '1285:1830', '1285:1829'], ['워크 · 도구', '1288:68', '1285:1842', '1285:1841']
  ];
  const currentRows = entries.map(([name, id, headerId, pageId]) => {
    const label = name + ' (페이지)';
    return { id, type: 'FRAME', name, children: [text(id + ':text', label, [
      link(label, name, node('', headerId)), link(label, '페이지', node('', pageId))
    ])] };
  });
  const extra = (id, label, target) => text(id, label, [link(label, label, node('', target))]);
  const archiveLine = '지난 기록은 91 · 보관 ‘지난 변경 기록’에 있습니다 →';
  return [
    { id: '897:760', name: '00 · 설계 관리 · 먼저 읽기', children: [
      { id: '1288:2', type: 'FRAME', name: '기능 지도', children: [...currentRows,
        extra('2208:28371', '전체 사용 흐름', 'f:1'), extra('w:link', '작업실', '897:761'),
        extra('r:link', '이전 작업실 보관', '2207:28518')] },
      { id: '898:31', type: 'FRAME', name: '변경 기록', children: overrides.log || [
        text('898:32', '변경 기록'),
        text('a:1', archiveLine, [link(archiveLine, '지난 변경 기록', node('', 'r:list'))]),
        text('a:2', 'C130 · 2026-10-29 · 고정 점검 도입 · PR #106 · 백업 없음'),
        text('a:3', 'C131 · 2026-10-30 · 화면 수정 · PR #107 · 백업 B066'),
        text('a:4', 'C132 · 2026-11-09 · 백업 칸 없이 쓰는 형식 · PR 없음')] }] },
    { id: '1284:3046', name: overrides.featureName || '공통 · 화면 틀', children: [
      { id: '1284:3047', type: 'FRAME', name: 'Header · 공통 · 화면 틀', children: overrides.header || [text('h:2', '최신판 3판 · 공통 기준')] },
      ...(overrides.feature || [])] },
    { id: '1284:3106', name: '업무 · 운영', children: [{ id: '1284:3107', type: 'FRAME', name: 'Header · 업무 · 운영' }] },
    { id: '1285:1829', name: '워크 · 업무 절차', children: [{ id: '1285:1830', type: 'FRAME', name: 'Header · 워크 · 업무 절차' }] },
    { id: '1285:1841', name: '워크 · 도구', children: [
      { id: '1285:1842', type: 'FRAME', name: 'Header · 워크 · 도구' },
      { id: 'f:1', type: 'FRAME', name: 'B10-1 · 도구 목록', children: [
      text('f:2', 'C66에서 작업실 → 공통-3으로 옮김')] }] },
    { id: '897:761', name: '70 · 작업실 · 실험·검토', children: [text('w:1', '작업실 사용 안내')] },
    { id: '1722:1395', name: '91 · 보관 · 기능 페이지 이전 판과 옛 설계', children: [
      { id: 'r:list', type: 'FRAME', name: '지난 변경 기록 · 목록', children: [
        text('r:1', 'C01  |  2026-10-01  |  Claude  |  공통-1 화면 정리'),
        text('r:2', 'C118 · 2026-10-28 KST · 워크-2 이전 화면을 보관으로 (백업 B056)'),
        text('r:3', 'C129 · 결과 확인 직접 표시')] },
      { id: 'old:1', type: 'FRAME', name: 'PREVIOUS · B5 · 옛 도구 화면', children: [] },
      { id: '2207:28518', type: 'FRAME', name: '92 · 보관 · 이전 작업실' }] },
  ];
}
async function check(pages) {
  const made = file(pages);
  const result = await new AsyncFunction('figma', code)(made.figma);
  return { result, calls: made.calls };
}

test('a file that follows the naming, log and link rules passes and reports the next number', async () => {
  const { result, calls } = await check(base());
  assert.deepEqual(result.errors, []);
  assert.equal(result.ok, true);
  assert.equal(result.next, 'C133');
  assert.equal(result.logLines, 3, 'lines with and without the old backup field both count');
  assert.ok(!('backups' in result));
  assert.equal(calls[calls.length - 1], '00 · 설계 관리 · 먼저 읽기');
});

test('numbered or status page names are errors', async () => {
  const { result } = await check(base({ featureName: '공통-1 · 화면 틀·이동 · 초안' }));
  assert.equal(result.ok, false);
  assert.ok(result.errors.some((e) => e.startsWith('이름: 공통-1')));
});

test('backup pages are errors until the product is completed once, and they are not opened', async () => {
  const pages = base();
  pages.push({ id: 'b:56', name: '99 · 백업 · B056 · 2026-10-28 · 도구 이전 화면 보관 전', children: [] },
             { id: 'b:66', name: 'B066 · 화면 수정 · 2026-10-30', children: [] });
  const { result, calls } = await check(pages);
  assert.equal(result.ok, false);
  assert.equal(result.errors.filter((e) => e.startsWith('백업 페이지: ')).length, 2);
  assert.ok(!calls.some((name) => name.startsWith('99 · ') || name.startsWith('B066')), 'backup pages are not opened');
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
  assert.ok(result.warnings.some((w) => w.startsWith('정리 신호: 공통 · 화면 틀 요소 1')));
  assert.ok(result.errors.some((e) => e.startsWith('00 글자 ')));
});

test('active page IDs, names, header parents and the four map entries agree', async () => {
  const pages = base({ feature: [{ id: 'p:1', type: 'FRAME', name: 'PREVIOUS20 · 업무 목업', children: [] }] });
  const { result } = await check(pages);
  assert.equal(result.ok, true);
  assert.deepEqual(result.activePages.map(({ id, header }) => [id, header]),
    [['1284:3046', '1284:3047'], ['1284:3106', '1284:3107'], ['1285:1829', '1285:1830'], ['1285:1841', '1285:1842']]);
  assert.ok(result.warnings.some((w) => w.startsWith('이전 판으로 보이는 이름: 공통 · 화면 틀 / PREVIOUS20')));
  pages.find(p => p.id === '1284:3106').children.push(...pages.find(p => p.id === '1285:1829').children.splice(0));
  pages.splice(pages.findIndex(p => p.id === '1285:1841'), 1);
  pages.push({ id: 'new:1', name: '워크 · 도구', children: [] });
  const broken = (await check(pages)).result;
  assert.equal(broken.ok, false);
  assert.ok(broken.errors.some(e => e.includes('활성 헤더 없음/위치 불일치: 1285:1830')));
  assert.ok(broken.errors.some(e => e.includes('등록되지 않은 활성 페이지: new:1')));
  assert.ok(broken.errors.some(e => e.includes('활성 페이지 없음: 1285:1841')));
});

test('the map must link to canonical headers, even when an old page or content link still resolves', async () => {
  const pages = base();
  const rows = pages[0].children[0].children;
  rows[0].children[0].links[0].hyperlink = { type: 'NODE', value: 'old:1' };
  rows[1].children[0].links[0].hyperlink = { type: 'NODE', value: '1284:3106' };
  const result = (await check(pages)).result;
  assert.equal(result.ok, false);
  assert.ok(result.errors.some(e => e.includes('기능 지도 진입점: 1288:11:text → old:1')));
  assert.ok(result.errors.some(e => e.includes('기능 지도에 없는 헤더: 1284:3047')));
  assert.ok(result.errors.some(e => e.includes('기능 지도에 없는 헤더: 1284:3107')));
  assert.ok(!result.errors.some(e => e.includes('2208:28371') || e.includes('2207:28518')));
});

test('a moved header reports its replacement; dated log links keep their original target', async () => {
  const pages = base();
  const old = { id: 'legacy:4', type: 'FRAME', name: 'Header · 공통 · 상태·부품', children: [] };
  pages[1].children.push(old, text('legacy:5', '옛 상태', [link('옛 상태', '옛 상태', node('', old.id))]));
  pages[0].children[1].children.push(text('legacy:6', 'C 기록의 옛 페이지', [
    link('C 기록의 옛 페이지', '옛 페이지', node('', '1284:3070'))]));
  const result = (await check(pages)).result;
  assert.equal(result.ok, true);
  assert.deepEqual(result.formerLinks, [{ from: 'legacy:5', target: 'legacy:4', current: '1284:3047' }]);
});

test('removing the feature map is an error', async () => {
  const pages = base();
  pages[0].children.shift();
  const result = (await check(pages)).result;
  assert.ok(result.errors.some(e => e.includes('00 기능 지도 1288:2을 찾지 못함')));
});

test('README sends each current feature to the same named header as the file checker', async () => {
  const { result } = await check(base());
  const readme = fs.readFileSync(path.join(__dirname, '..', 'README.md'), 'utf8');
  const index = readme.split('<a id="figma-active-pages"></a>')[1].split('### 설계 문서의 역할')[0];
  const rows = [...index.matchAll(/^\| \[([^\]]+)\]\(https:\/\/www\.figma\.com\/design\/([A-Za-z0-9]+)\?node-id=(\d+)-(\d+)\)/gm)]
    .map(([, name, key, first, last]) => ({ name, key, header: first + ':' + last }));
  assert.deepEqual(rows, result.activePages.map(({ name, header }) => ({ name, key: KEY, header })));
});
