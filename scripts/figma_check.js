// Figma 설계 파일 고정 점검 (읽기 전용, 2026-10-29 C130)
// 실행: 이 파일 내용 전체를 Figma MCP use_figma의 code로 넘긴다 (파일 XK2wTos6sEuxSHhIj7cqg6).
// Figma를 고친 뒤, 00 변경 기록에 한 줄을 쓰기 전에 실행한다. 아무것도 고치지 않고 보고만 한다.
// 기준 숫자는 아래 LIMITS 한 곳에만 둔다. 규칙 원문: AGENTS.md의 Figma 항목, Figma 00 · 설계 관리.
const LIMITS = {
  featureNodes: 10000, // 기능 페이지 요소 수 (페이지를 열고 인스턴스 안까지 센 값) — 넘으면 정리 신호
  featureChars: 50000, // 기능 페이지 글자 수 — 넘으면 정리 신호
  adminChars: 20000,   // 00 · 설계 관리 글자 수 — 넘으면 오류
  logLines: 20,        // 00 변경 기록 줄 수 — 넘으면 오래된 줄을 91로
  lineChars: 200,      // 변경 기록 한 줄 길이
};
const FILE_KEY = 'XK2wTos6sEuxSHhIj7cqg6';
const LOG_ID = '898:31'; // 00 변경 기록
const MAP_ID = '1288:2'; // 00 기능 지도
const ARCHIVE_LIST = '지난 변경 기록 · 목록'; // 91 보관에서 지난 기록을 모은 프레임 이름
const LINE = /^C(\d+) · (\d{4}-\d{2}-\d{2}) · (.+) · (PR #\d+|PR 없음) · (백업 B\d{3}|백업 없음)$/;
const OLD_TERMS = [/(공통|업무|워크)-\d/, /페이지 이름 끝/];

const started = Date.now(), errors = [], warnings = [];
const kindOf = (name) => /^00 · /.test(name) ? 'admin' : /^70 · /.test(name) ? 'workshop'
  : /^9[12] · 보관 · /.test(name) ? 'archive' : /^99 · |^(백업 )?B\d{3} · /.test(name) ? 'backup' : 'feature';
const walk = (root, fn) => {
  const stack = [root];
  while (stack.length) {
    const node = stack.pop();
    fn(node);
    if ('children' in node && node.children) for (const child of node.children) stack.push(child);
  }
};
const inside = (node, root) => { for (let p = node; p; p = p.parent) if (p === root) return true; return false; };
const pageOf = (node) => { let p = node; while (p && p.type !== 'PAGE') p = p.parent; return p; };
const cache = new Map();
const get = async (id) => { if (!cache.has(id)) cache.set(id, await figma.getNodeByIdAsync(id)); return cache.get(id); };
const links = (text) => {
  if (!text.characters.length) return [];
  const out = [];
  for (const seg of text.getStyledTextSegments(['hyperlink'])) {
    const h = seg.hyperlink;
    if (!h) continue;
    let id = null;
    if (h.type === 'NODE') id = h.value;
    if (h.type === 'URL') {
      const m = /figma\.com\/(?:design|file)\/([A-Za-z0-9]+)[^?#]*\?[^#]*node-id=(\d+)(?:-|:|%3A)(\d+)/.exec(h.value);
      if (m && m[1] === FILE_KEY) id = m[2] + ':' + m[3];
    }
    if (id) out.push({ id, label: text.characters.slice(seg.start, seg.end) });
  }
  return out;
};

// 1) 페이지 이름·크기
const pages = figma.root.children, sizes = [], features = [], texts = [], backups = [], seen = new Set();
let logFrame = null, archiveList = null;
for (const page of pages) {
  const kind = kindOf(page.name);
  if (kind === 'backup') {
    const m = /^99 · 백업 · (B\d{3}) · (\d{4}-\d{2}-\d{2}) · (.+ 전)$/.exec(page.name);
    if (!m) { errors.push('백업 이름: ' + page.name); continue; }
    if (seen.has(m[1])) errors.push('백업 번호 중복: ' + m[1]);
    seen.add(m[1]);
    backups.push({ b: m[1], date: m[2] });
    continue; // 백업 안의 사본은 크기·글 점검에서 뺀다
  }
  if (kind === 'feature') {
    features.push(page);
    if (!/^(공통|업무|워크) · \S/.test(page.name) || /(공통|업무|워크)-\d|초안|구현|사내 확인|\d+판|확정|현재|최신|이전/.test(page.name))
      errors.push('이름: ' + page.name + ' (‘구역 · 왼쪽 메뉴 이름’, 번호·상태 없음)');
  }
  await figma.setCurrentPageAsync(page); // 열어야 인스턴스 안까지 셀 수 있다
  let nodes = 0, chars = 0;
  walk(page, (node) => {
    if (node === page) return;
    nodes++;
    if (node.type === 'TEXT') { chars += node.characters.length; if (kind !== 'archive') texts.push(node); }
    if (node.id === LOG_ID) logFrame = node;
    if (kind === 'archive' && node.name === ARCHIVE_LIST) archiveList = node;
  });
  sizes.push([page.name.slice(0, 24), nodes, chars]);
  if (kind === 'feature' && (nodes > LIMITS.featureNodes || chars > LIMITS.featureChars))
    warnings.push('정리 신호: ' + page.name + ' 요소 ' + nodes + ' · 글자 ' + chars + ' (기준 ' + LIMITS.featureNodes + ' · ' + LIMITS.featureChars + ')');
  if (kind === 'admin' && chars > LIMITS.adminChars) errors.push('00 글자 ' + chars + ' > ' + LIMITS.adminChars + ' (오래된 기록을 91로)');
}
for (const page of features) for (const child of page.children)
  if (!/^Header · /.test(child.name) && /PREVIOUS|대체됨|이전 판|현재|최신|확정|\d+판/.test(child.name))
    warnings.push('이전 판으로 보이는 이름: ' + page.name + ' / ' + child.name.slice(0, 40));

// 2) 현재 안내의 옛 표기 (변경 기록과 ‘C##에서 옮김’ 같은 이력 문장은 뺀다)
for (const text of texts) {
  if (logFrame && inside(text, logFrame)) continue;
  const s = text.characters;
  if (/C\d+에서/.test(s)) continue;
  for (const term of OLD_TERMS) {
    const at = s.search(term);
    if (at >= 0) { errors.push('옛 표기: ' + text.id + ' “' + s.slice(Math.max(0, at - 12), at + 24) + '”'); break; }
  }
}

// 3) 링크: 없는 노드, 최신 안내가 보관 안의 화면을 가리키는 경우
for (const text of texts) for (const link of links(text)) {
  const target = await get(link.id);
  if (!target) { errors.push('없는 노드 링크: ' + text.id + ' → ' + link.id + ' “' + link.label.slice(0, 24) + '”'); continue; }
  if (target.type === 'PAGE' || (logFrame && inside(text, logFrame))) continue;
  const where = pageOf(target);
  if (where && /^(archive|backup)$/.test(kindOf(where.name)) && !/이전|보관|지난|PREVIOUS|백업/.test(link.label))
    warnings.push('보관을 가리키는 링크: ' + text.id + ' “' + link.label.slice(0, 24) + '” → ' + link.id);
}
const map = await get(MAP_ID), mapped = new Set();
if (map) walk(map, (node) => { if (node.type === 'TEXT') for (const link of links(node)) mapped.add(link.id); });
for (const page of features) if (!mapped.has(page.id)) warnings.push('기능 지도에 없는 기능 페이지: ' + page.name);

// 4) 00 변경 기록: 한 줄 형식·줄 수·번호
const lines = [], archived = archiveList ? archiveList.children.filter((n) => n.type === 'TEXT') : [];
if (!logFrame) errors.push('00 변경 기록 ' + LOG_ID + '을 찾지 못함');
else for (const node of logFrame.children) if (node.type === 'TEXT' && /^C\d+ · /.test(node.characters)) lines.push(node.characters);
if (!archiveList) warnings.push('91 보관에 ‘' + ARCHIVE_LIST + '’ 프레임이 없음');
if (lines.length > LIMITS.logLines) errors.push('00 변경 기록 ' + lines.length + '줄 > ' + LIMITS.logLines + ' (오래된 줄을 91 ‘' + ARCHIVE_LIST + '’ 끝으로)');
const number = (s) => { const m = /^C(\d+)/.exec(s); return m ? +m[1] : null; };
const archivedMax = Math.max(0, ...archived.map((n) => number(n.characters) || 0));
const used = new Set();
for (const s of lines) {
  const c = number(s);
  if (s.length > LIMITS.lineChars || s.indexOf('\n') >= 0 || !LINE.test(s)) errors.push('한 줄 형식 아님: ' + s.slice(0, 40));
  if (used.has(c)) errors.push('변경 기록 번호 중복: C' + c);
  if (c <= archivedMax) errors.push('번호가 보관된 마지막 기록 C' + archivedMax + '보다 작음: C' + c);
  used.add(c);
}
const next = 'C' + (Math.max(archivedMax, ...lines.map(number)) + 1);

// 5) 백업: 처음 언급한 기록(= 만든 기록)과 한 줄 기록의 PR. PR 병합 여부는 GitHub에서 확인한다.
const first = new Map();
for (const s of archived.map((n) => n.characters).concat(lines)) {
  const one = LINE.exec(s), re = /B(\d{3})/g;
  let m;
  while ((m = re.exec(s))) if (!first.has('B' + m[1])) first.set('B' + m[1], { c: number(s) ? 'C' + number(s) : '?', pr: one ? one[4] : 'PR 확인 필요' });
}
const backupReport = backups.map((b) => {
  const f = first.get(b.b);
  if (!f) warnings.push('백업을 만든 기록이 없음: ' + b.b);
  return [b.b, b.date, f ? f.c : '?', f ? f.pr : 'PR 확인 필요'];
});

await figma.setCurrentPageAsync(pages[0]);
const cap = (list) => list.length > 40 ? list.slice(0, 40).concat(['… 외 ' + (list.length - 40) + '건']) : list;
return { ok: errors.length === 0, errors: cap(errors), warnings: cap(warnings), next, logLines: lines.length,
  ms: Date.now() - started, sizes, backups: backupReport };
