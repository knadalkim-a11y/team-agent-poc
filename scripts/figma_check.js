// Figma 설계 파일 고정 점검 (읽기 전용, 활성 기능 페이지 4개)
// 실행: 이 파일 내용 전체를 Figma MCP use_figma의 code로 넘긴다 (파일 XK2wTos6sEuxSHhIj7cqg6).
// Figma를 고친 뒤, 00 변경 기록에 한 줄을 쓰기 전에 실행한다. 아무것도 고치지 않고 보고만 한다.
// 기준 숫자는 아래 LIMITS 한 곳에만 둔다. 규칙 원문: AGENTS.md의 Figma 항목, Figma 00 · 설계 관리.
// 구역 구조: docs/mockups/ees-work/TASK.md#figma-page-structure-20261110
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
// Keep the original outer headers: links to current designs survive a screen revision.
// sectioned: 맨 위에 머리말과 구역(Section)만 두는 페이지. 2026-11-11 '워크 · 도구' 시범부터 옮긴 페이지에만
// 검사하고, 네 페이지를 다 옮기면 모든 기능 페이지에 적용한다 (TASK 계획 6단계).
const ACTIVE_PAGES = [
  { id: '1284:3046', name: '공통 · 화면 틀', header: '1284:3047', row: '1288:11', former: ['1284:3058', '1284:3070', '1285:1853'] },
  { id: '1284:3106', name: '업무 · 운영', header: '1284:3107', row: '1288:42', former: ['1689:1061', '1689:1062', '1689:1063', '1284:3118'], sectioned: true },
  { id: '1285:1829', name: '워크 · 업무 절차', header: '1285:1830', row: '1288:63', former: ['1283:3107', '1285:1865'] },
  { id: '1285:1841', name: '워크 · 도구', header: '1285:1842', row: '1288:68', former: [], sectioned: true }
];
const byPage = new Map(ACTIVE_PAGES.map((item) => [item.id, item]));
const byHeader = new Map(ACTIVE_PAGES.map((item) => [item.header, item]));
const byFormer = new Map(ACTIVE_PAGES.flatMap((item) => item.former.map((id) => [id, item])));
const ARCHIVE_LIST = '지난 변경 기록 · 목록'; // 91 보관에서 지난 기록을 모은 프레임 이름
// From C165 a line ends with the PR. Lines up to C164 keep their ' · 백업 …' field as written then.
const LINE = /^C(\d+) · (\d{4}-\d{2}-\d{2}) · (.+) · (PR #\d+|PR 없음)(?: · (백업 B\d{3}|백업 없음))?$/;
const OLD_TERMS = [/(공통|업무|워크)-\d/, /페이지 이름 끝/];
const STALE_NAME = /PREVIOUS|대체됨|이전 판|현재|최신|확정|\d+판/; // 기능 페이지 화면 이름에 남은 판·상태

const started = Date.now(), errors = [], warnings = [];
const kindOf = (name) => /^00 · /.test(name) ? 'admin' : /^70 · /.test(name) ? 'workshop'
  : /^9[12] · 보관(?: · |$)/.test(name) ? 'archive' : /^99 · |^(백업 )?B\d{3} · /.test(name) ? 'backup' : 'feature';
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
const pages = figma.root.children, sizes = [], features = [], texts = [];
let logFrame = null, archiveList = null;
for (const page of pages) {
  const kind = kindOf(page.name);
  const canonical = byPage.get(page.id);
  if (canonical && page.name !== canonical.name) errors.push('활성 페이지 이름: ' + page.id + ' “' + page.name + '” → “' + canonical.name + '”');
  if (kind === 'backup') {
    // 2026-11-10 사용자 결정: 제품을 한 번 완성하기 전에는 백업 페이지와 복구 절차를 두지 않는다.
    errors.push('백업 페이지: ' + page.name + ' (제품을 한 번 완성하기 전에는 백업 페이지를 두지 않음)');
    continue; // 열지 않는다
  }
  if (kind === 'feature') {
    features.push(page);
    if (!canonical) errors.push('등록되지 않은 활성 페이지: ' + page.id + ' “' + page.name + '”');
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
  if (!/^Header · /.test(child.name) && STALE_NAME.test(child.name))
    warnings.push('이전 판으로 보이는 이름: ' + page.name + ' / ' + child.name.slice(0, 40));

// 1b) 구역: 옮긴 페이지는 맨 위에 머리말과 구역만 두고, 머리말의 색인에서 모든 구역으로 링크한다
const sections = [];
for (const item of ACTIVE_PAGES.filter((entry) => entry.sectioned)) {
  const page = features.find((p) => p.id === item.id);
  if (!page) continue; // 페이지가 없으면 3)의 활성 페이지 검사가 보고한다
  const header = page.children.find((node) => node.id === item.header);
  if (!header) errors.push('머리말이 맨 위에 없음: ' + page.name + ' (' + item.header + ')');
  const indexed = new Set();
  if (header) walk(header, (node) => { if (node.type === 'TEXT') for (const link of links(node)) indexed.add(link.id); });
  for (const child of page.children) {
    if (child === header) continue;
    if (child.type !== 'SECTION') { errors.push('구역 밖 요소: ' + page.name + ' / ' + child.name.slice(0, 40) + ' (' + child.id + ')'); continue; }
    if (!indexed.has(child.id)) errors.push('머리말 색인에 없는 구역: ' + page.name + ' / ' + child.name);
    if (/\d|PREVIOUS|대체됨|이전|현재|최신|확정|초안|구현|사내 확인/.test(child.name))
      warnings.push('구역 이름에 번호·판·상태: ' + page.name + ' / ' + child.name);
    let nodes = 0, chars = 0;
    walk(child, (node) => { if (node === child) return; nodes++; if (node.type === 'TEXT') chars += node.characters.length; });
    sections.push([page.name, child.name, nodes, chars]);
    if (nodes > LIMITS.featureNodes / 2 || chars > LIMITS.featureChars / 2)
      warnings.push('구역 크기: ' + page.name + ' / ' + child.name + ' 요소 ' + nodes + ' · 글자 ' + chars
        + ' (페이지 기준의 절반 초과 · 따로 고쳐지는 구역이면 새 페이지로 나눌지 사용자에게 묻기)');
    for (const frame of child.children)
      if (!/^Header · /.test(frame.name) && STALE_NAME.test(frame.name))
        warnings.push('이전 판으로 보이는 이름: ' + page.name + ' / ' + child.name + ' / ' + frame.name.slice(0, 40));
  }
}

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
const formerLinks = [];
for (const text of texts) for (const link of links(text)) {
  const target = await get(link.id);
  const historical = logFrame && inside(text, logFrame);
  // Former page IDs can survive in dated records. Report the current header without
  // requiring every preserved frame under the old header to become a redirect.
  const former = byFormer.get(link.id);
  const oldHeader = target && !byHeader.has(target.id) && /^Header · /.test(target.name || '');
  if (!historical && (former || oldHeader)) {
    const owner = target && pageOf(target);
    const destination = former || (owner && (byFormer.get(owner.id) || byPage.get(owner.id)));
    formerLinks.push({ from: text.id, target: link.id, current: destination?.header || null });
  }
  if (!target && former && historical) continue;
  if (!target) { errors.push('없는 노드 링크: ' + text.id + ' → ' + link.id + ' “' + link.label.slice(0, 24) + '”'); continue; }
  if (historical) continue;
  const where = pageOf(target);
  if (where && /^(archive|backup)$/.test(kindOf(where.name)) && !/이전|보관|지난|PREVIOUS|백업/.test(link.label))
    warnings.push('보관을 가리키는 링크: ' + text.id + ' “' + link.label.slice(0, 24) + '” → ' + link.id);
}
// Only the four current feature rows own an official header. The map can also
// link to the workshop, archives and an end-to-end example.
const map = await get(MAP_ID);
if (!map || kindOf(pageOf(map)?.name || '') !== 'admin') errors.push('00 기능 지도 ' + MAP_ID + '을 찾지 못함');
for (const item of ACTIVE_PAGES) {
  const page = pages.find((p) => p.id === item.id);
  if (!page || kindOf(page.name) !== 'feature') errors.push('활성 페이지 없음: ' + item.id + ' “' + item.name + '”');
  const header = await get(item.header);
  if (!header || header.type !== 'FRAME' || pageOf(header)?.id !== item.id) {
    errors.push('활성 헤더 없음/위치 불일치: ' + item.header + ' → ' + item.id + ' “' + item.name + '”');
  }
  const row = await get(item.row);
  if (!row || !map || !inside(row, map)) {
    errors.push('기능 지도 행 없음: ' + item.row + ' “' + item.name + '”');
    continue;
  }
  const rowLinks = [];
  walk(row, (node) => {
    if (node.type === 'TEXT') for (const link of links(node)) rowLinks.push({ from: node.id, ...link });
  });
  if (!rowLinks.some(link => link.id === item.header)) {
    errors.push('기능 지도에 없는 헤더: ' + item.header + ' “' + item.name + '”');
  }
  for (const link of rowLinks) {
    if (link.id !== item.header && link.id !== item.id) {
      errors.push('기능 지도 진입점: ' + link.from + ' → ' + link.id + ' “' + link.label + '” (해당 페이지/헤더 사용)');
    }
  }
}

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

await figma.setCurrentPageAsync(pages[0]);
const cap = (list) => list.length > 40 ? list.slice(0, 40).concat(['… 외 ' + (list.length - 40) + '건']) : list;
return { ok: errors.length === 0, errors: cap(errors), warnings: cap(warnings), next, logLines: lines.length,
  ms: Date.now() - started, sizes, sections: cap(sections),
  activePages: ACTIVE_PAGES.map(({ id, name, header }) => ({ id, name, header })), formerLinks: cap(formerLinks) };
