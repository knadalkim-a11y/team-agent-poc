// Figma 기능 페이지 구조 조사 (읽기 전용). 2026-11-10 구조 개선의 단계마다 옮기기 전후를 값으로 비교한다.
// 실행: PAGE_IDS와 NEW_IDS를 바꿔 이 파일 내용 전체를 use_figma의 code로 넘긴다 (파일 XK2wTos6sEuxSHhIj7cqg6).
// 페이지를 바꾸지 않고 불러서(loadAsync) 읽는다. 계획: docs/mockups/ees-work/TASK.md#figma-page-structure-20261110
const PAGE_IDS = ['1284:3046', '1284:3106', '1285:1829', '1285:1841', '897:761']; // 네 기능 페이지와 70 작업실
const NEW_IDS = []; // 그 단계에서 새로 만든 구역·색인 글. ID 해시에서 뺀다 (안의 기존 요소는 그대로 센다)
const SAMPLES = ['2017:76', '2052:358', '2018:194']; // 이 페이지에 있는 것만 PNG로 내보내 해시를 낸다
const SKIP_TREES = []; // 다른 페이지로 옮길 요소. 그 아래 전체를 페이지의 수·해시·링크에서 뺀다
const TREES = []; // 어느 페이지에 있든 따로 요약할 요소: 아래 전체의 ID·배치·인스턴스 해시, 수, PNG 해시
const FILE_KEY = 'XK2wTos6sEuxSHhIj7cqg6';

const started = Date.now();
const skip = new Set(NEW_IDS);
const hex = (h) => (h >>> 0).toString(16).padStart(8, '0');
const fnv = (s) => { let h = 0x811c9dc5; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 0x01000193); } return hex(h); };
const fnvBytes = (b) => { let h = 0x811c9dc5; for (let i = 0; i < b.length; i++) { h ^= b[i]; h = Math.imul(h, 0x01000193); } return hex(h); };
const r = (v) => Math.round(v * 100) / 100;
const at = (n) => [r(n.absoluteTransform[0][2]), r(n.absoluteTransform[1][2])]; // 캔버스 위치 (구역 안이어도 같은 기준)
const walk = (root, fn) => {
  const stack = [root];
  while (stack.length) { const n = stack.pop(); fn(n); if ('children' in n && n.children) for (const c of n.children) stack.push(c); }
};
const stat = (root) => {
  let nodes = 0, chars = 0, inst = 0;
  walk(root, (n) => { nodes++; if (n.type === 'TEXT') chars += n.characters.length; if (n.type === 'INSTANCE') inst++; });
  return [nodes, chars, inst];
};
async function inventory(page) {
  await page.loadAsync();
  const skipTrees = new Set(SKIP_TREES);
  const walkPage = (fn) => {
    const stack = [...page.children];
    while (stack.length) { const n = stack.pop(); if (skipTrees.has(n.id)) continue; fn(n); if ('children' in n && n.children) for (const c of n.children) stack.push(c); }
  };
  const row = (n) => [n.id, n.name, n.type, ...at(n), r(n.width), r(n.height), ...stat(n)];
  const header = page.children.find((n) => /^Header · /.test(n.name)) || null;
  const inHeader = (n) => { for (let p = n; p && p !== page; p = p.parent) if (p === header) return true; return false; };
  // 맨 위 요소: 부모가 페이지나 구역인 가장 바깥 요소. 그 안의 배치는 요소를 옮기거나 구역에 넣어도 같아야 한다
  const rootOf = (n) => { let x = n; while (x.parent && x.parent.type !== 'PAGE' && x.parent.type !== 'SECTION') x = x.parent; return x; };

  // 맨 위 요소 (구역이면 안의 요소까지)
  const top = page.children.filter((n) => !skipTrees.has(n.id)).map((n) => n.type === 'SECTION' ? [...row(n), n.children.map(row)] : row(n));

  // 전후 비교용 해시: 노드 ID, 캔버스 위치·크기, 맨 위 요소 안의 배치, 인스턴스 → 원본 부품
  // (위치·배치에서 머리말은 뺀다. 색인 줄이 늘어나므로 머리말 글은 따로 기록한다)
  const ids = [], geo = [], lay = [], texts = [], inst = [];
  let nodes = 0, chars = 0;
  walkPage((n) => {
    nodes++;
    if (n.type === 'TEXT') { chars += n.characters.length; texts.push(n); }
    if (n.type === 'INSTANCE') inst.push(n);
    if (skip.has(n.id)) return;
    ids.push(n.id);
    if (inHeader(n)) return;
    const size = ',' + r(n.width) + 'x' + r(n.height);
    geo.push(n.id + '@' + at(n).join(',') + size);
    if (n.type === 'SECTION') return;
    const a = at(n), b = at(rootOf(n));
    lay.push(n.id + '@' + r(a[0] - b[0]) + ',' + r(a[1] - b[1]) + size);
  });
  const pairs = [], mains = new Set();
  for (const n of inst) {
    const m = await n.getMainComponentAsync();
    const id = m ? m.id : 'none';
    mains.add(id);
    pairs.push(n.id + '>' + id);
  }

  // 링크 목록 [글 ID, 시작 위치, 대상, 링크 글자]. 이 파일의 노드는 ID로, 그 밖의 주소는 github·figma만 그대로 둔다
  const links = [];
  for (const t of texts) {
    if (!t.characters.length) continue;
    for (const s of t.getStyledTextSegments(['hyperlink'])) {
      const h = s.hyperlink;
      if (!h) continue;
      let target = h.value;
      if (h.type === 'URL') {
        const m = /figma\.com\/(?:design|file)\/([A-Za-z0-9]+)[^?#]*\?[^#]*node-id=(\d+)(?:-|:|%3A)(\d+)/.exec(h.value);
        const host = (/^[a-z]+:\/\/([^/?#]+)/i.exec(h.value) || [])[1] || '';
        target = m && m[1] === FILE_KEY ? 'url:' + m[2] + ':' + m[3] : /(^|\.)(github|figma)\.com$/.test(host) ? h.value : 'host:' + host;
      }
      links.push([t.id, s.start, target, t.characters.slice(s.start, s.end).slice(0, 40)]);
    }
  }
  links.sort((a, b) => a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : a[1] - b[1]);

  // 머리말 글 (다음 단계에서 색인 줄을 넣을 때 기준)
  const color = (p) => p && p.type === 'SOLID' ? [r(p.color.r), r(p.color.g), r(p.color.b), r(p.opacity === undefined ? 1 : p.opacity)] : null;
  const headerTexts = header ? header.children.filter((n) => n.type === 'TEXT').map((t) => [t.id, t.name, t.characters,
    t.getStyledTextSegments(['fontName', 'fontSize', 'fills', 'textDecoration']).map((s) =>
      [s.start, s.end, s.fontName.family + ' ' + s.fontName.style, s.fontSize, color(s.fills[0]), s.textDecoration])]) : [];

  // 표본 화면: 프레임만 PNG로 내보낸 바이트의 해시 (부모 구역의 배경은 들어가지 않는다)
  const samples = {};
  for (const id of SAMPLES) {
    const n = await figma.getNodeByIdAsync(id);
    let p = n;
    while (p && p.type !== 'PAGE') p = p.parent;
    if (!n || p !== page) continue;
    const bytes = await n.exportAsync({ format: 'PNG', constraint: { type: 'SCALE', value: 1 } });
    samples[id] = [fnvBytes(bytes), bytes.length];
  }
  return { page: [page.id, page.name],
    nodes, chars, instances: inst.length, mainComponents: mains.size,
    digest: { ids: [ids.length, fnv(ids.sort().join(','))], geometry: [geo.length, fnv(geo.sort().join('|'))],
      layout: [lay.length, fnv(lay.sort().join('|'))], instances: [pairs.length, fnv(pairs.sort().join(','))] },
    top, header: header ? [...row(header), headerTexts] : null, links, samples };
}
// 따로 요약할 요소: 페이지를 옮겨도 같아야 하는 값 (위치는 요소 기준, 캔버스 위치는 따로 적는다)
async function trees(ids) {
  const out = [];
  for (const id of ids) {
    const root = await figma.getNodeByIdAsync(id);
    let p = root;
    while (p && p.type !== 'PAGE') p = p.parent;
    if (p) await p.loadAsync();
    const all = [], lay = [], inst = [];
    const b = at(root);
    walk(root, (n) => {
      all.push(n.id);
      const a = at(n);
      lay.push(n.id + '@' + r(a[0] - b[0]) + ',' + r(a[1] - b[1]) + ',' + r(n.width) + 'x' + r(n.height));
      if (n.type === 'INSTANCE') inst.push(n);
    });
    const pairs = [];
    for (const n of inst) { const m = await n.getMainComponentAsync(); pairs.push(n.id + '>' + (m ? m.id : 'none')); }
    const bytes = await root.exportAsync({ format: 'PNG', constraint: { type: 'SCALE', value: 1 } });
    out.push({ id, name: root.name, page: p ? p.id : null, parent: root.parent.id, at: b, size: [r(root.width), r(root.height)], counts: stat(root),
      ids: [all.length, fnv(all.sort().join(','))], layout: [lay.length, fnv(lay.sort().join('|'))],
      instances: [pairs.length, fnv(pairs.sort().join(','))], png: [fnvBytes(bytes), bytes.length] });
  }
  return out;
}
const pages = [];
for (const id of PAGE_IDS) pages.push(await inventory(await figma.getNodeByIdAsync(id)));
return { marker: 'figma-structure-inventory', newIds: NEW_IDS, skipTrees: SKIP_TREES, ms: Date.now() - started,
  columns: ['id', 'name', 'type', 'x', 'y', 'w', 'h', 'nodes', 'chars', 'instances', 'children'], pages,
  trees: TREES.length ? await trees(TREES) : [] };
