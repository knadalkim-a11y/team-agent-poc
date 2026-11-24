/* Work list edits keep the saved procedure tree and all job IDs. */
function createWorkTaskLayout() {
  const items = definition => Array.isArray(definition?.nodes) ? definition.nodes : Object.values(definition?.nodes || {});
  const parentId = node => node?.parent_id || node?.parent;
  const isLoose = stage => stage?.type === 't' && stage.ungrouped === true;
  const untitled = '작업';
  const structuralKeys = new Set(['id', 'type', 'name', 'parent', 'parent_id', 'children', 'ungrouped']);
  const optionalStageFields = new Set(['description', 'instructions', 'deps', 'inputs', 'condition', 'completion']);
  const noValue = value => value == null || value === '' || (typeof value === 'object' && !Object.keys(value).length);
  const validId = id => typeof id === 'string' && /^[A-Za-z0-9_.:-]{1,160}$/.test(id) && !['__proto__', 'constructor', 'prototype'].includes(id);

  function setParent(node, id) {
    if (parentId(node) === id) return;
    node.parent = id;
    if (Object.hasOwn(node, 'parent_id')) node.parent_id = id;
  }

  function put(definition, node) {
    if (Array.isArray(definition.nodes)) definition.nodes.push(node);
    else definition.nodes[node.id] = node;
  }

  function remove(definition, ids) {
    if (!ids.size) return;
    if (Array.isArray(definition.nodes)) definition.nodes = definition.nodes.filter(node => !ids.has(node?.id));
    else for (const id of ids) delete definition.nodes[id];
  }

  function usesStage(node, id) {
    if ([node.deps, node.api_generated_deps].some(refs => Array.isArray(refs) && refs.includes(id)) || node.result_source_job_id === id || node.effect_job_id === id || node.effect_criterion?.job_id === id) return true;
    const bindings = [...Object.values(node.argument_bindings || {}), ...Object.values(node.api_binding?.inputs || {})];
    return bindings.some(binding => binding?.result?.job_id === id);
  }

  function stageDataReason(definition, stage, nodes) {
    const id = stage.id;
    if (Object.hasOwn(definition.schedule?.stage_deadlines || {}, id)) return '이 단계의 기한 설정을 먼저 정리해 주세요.';
    if (Object.hasOwn(definition.factory_overrides || {}, id)) return '이 단계의 공장별 설정을 먼저 정리해 주세요.';
    if (nodes.some(node => node !== stage && usesStage(node, id))) return '이 단계를 참조하는 작업의 연결을 먼저 변경해 주세요.';
    // Older editors wrote these defaults even for a group with just a name.
    const defaults = {mode:'human', result_block:'human_confirm', human_confirmation:true};
    const configured = Object.entries(stage).some(([key, value]) => {
      if (structuralKeys.has(key) || (optionalStageFields.has(key) && noValue(value))) return false;
      if (key === 'completion' && Object.keys(value).length === 1 && value.rule === '') return false;
      return !Object.hasOwn(defaults, key) || defaults[key] !== value;
    });
    return configured ? '이 단계의 설명 또는 추가 설정을 먼저 정리해 주세요.' : '';
  }

  function inspect(definition) {
    const nodes = items(definition).filter(node => node?.id);
    const byId = new Map(nodes.map(node => [node.id, node]));
    const roots = nodes.filter(node => node.type === 'p');
    const root = roots[0];

    function children(owner, types) {
      const listed = owner.children ?? [];
      const actual = nodes.filter(node => parentId(node) === owner.id);
      const ordered = Array.isArray(listed) ? listed.map(id => byId.get(id)) : [];
      const valid = Array.isArray(listed) && new Set(listed).size === listed.length && ordered.length === actual.length &&
        ordered.every(node => node && parentId(node) === owner.id && types.includes(node.type));
      if (valid) return {ordered, valid};
      // Still show legacy rows that can be read. Editing a broken links list could drop data.
      const linked = ordered.filter(node => node && parentId(node) === owner.id && types.includes(node.type));
      return {ordered:[...new Set([...linked, ...actual.filter(node => types.includes(node.type))])], valid};
    }

    const top = root ? children(root, ['t', 'j']) : {ordered:[], valid:false};
    let valid = top.valid && roots.length === 1 && byId.size === nodes.length;
    const units = [], loose = [];
    for (const node of top.ordered) {
      if (node.type === 'j') { units.push({stage:null, job:node}); continue; }
      if (!isLoose(node) || node.name !== untitled || stageDataReason(definition, node, nodes)) { units.push({stage:node}); continue; }
      const jobs = children(node, ['j']);
      valid &&= jobs.valid;
      loose.push(node);
      units.push(...jobs.ordered.map(job => ({stage:node, job})));
    }
    return {nodes, byId, root, units, loose, children, valid};
  }

  function freshId(used, allocate) {
    const id = allocate?.();
    if (!validId(id) || used.has(id)) return '';
    used.add(id);
    return id;
  }

  function looseStage(id, rootId) {
    return {id, type:'t', parent:rootId, name:untitled, children:[], ungrouped:true};
  }

  // Consecutive loose rows share an internal stage. Retain its ID when possible.
  // Prepare a full plan before changing either child links or the node collection.
  function writeUnits(definition, graph, units, allocate, {added, removed} = {}) {
    const used = new Set(graph.byId.keys());
    if (added) used.add(added.id);
    const reusable = new Set(graph.loose), plan = [];
    let block = null;
    for (const unit of units) {
      if (!unit.job || !unit.stage) {
        plan.push({node:unit.job || unit.stage});
        block = null;
        continue;
      }
      if (!block) { block = {loose:[]}; plan.push(block); }
      block.loose.push(unit);
    }
    for (const entry of plan) {
      if (!entry.loose) continue;
      const existing = entry.loose.find(unit => reusable.has(unit.stage))?.stage;
      if (existing) { entry.node = existing; reusable.delete(existing); continue; }
      const id = freshId(used, allocate);
      if (!id) return false;
      entry.node = looseStage(id, graph.root.id);
      entry.created = true;
    }

    const retired = new Set([...reusable].map(stage => stage.id));
    if (removed) retired.add(removed.id);
    remove(definition, retired);
    if (added) {
      put(definition, added);
      for (const id of added.children) setParent(graph.byId.get(id), added.id);
    }
    for (const {node, loose, created} of plan) {
      if (!loose) continue;
      if (created) put(definition, node);
      node.children = loose.map(({job}) => job.id);
      for (const {job} of loose) setParent(job, node.id);
    }
    graph.root.children = plan.map(({node}) => node.id);
    return true;
  }

  function addLooseJob(definition, job, nextStageId) {
    const graph = inspect(definition);
    if (!graph.valid || job?.type !== 'j' || !validId(job.id) || graph.byId.has(job.id)) return false;
    if (job.children != null && (!Array.isArray(job.children) || job.children.length)) return false;
    const lastId = graph.root.children?.at(-1);
    const used = new Set([...graph.byId.keys(), job.id]);
    let stage = graph.loose.find(node => node.id === lastId);
    if (!stage) {
      const id = freshId(used, nextStageId);
      if (!id) return false;
      stage = looseStage(id, graph.root.id);
      put(definition, stage);
      graph.root.children = [...(graph.root.children || []), id];
    }
    setParent(job, stage.id);
    stage.children = [...(stage.children || []), job.id];
    put(definition, job);
    return true;
  }

  function group(definition, jobIds, name, nextStageId, groupId) {
    const graph = inspect(definition);
    const title = typeof name === 'string' ? name.trim() : '';
    if (!graph.valid || !title || title.length > 160 || !Array.isArray(jobIds) || !jobIds.length) return null;
    const selected = new Set(jobIds);
    const positions = graph.units.flatMap(({job}, index) => job && selected.has(job.id) ? [index] : []);
    if (positions.length !== jobIds.length || positions.at(-1) - positions[0] + 1 !== positions.length) return null;
    const id = freshId(new Set(graph.byId.keys()), groupId === undefined ? nextStageId : () => groupId);
    if (!id) return null;
    const units = graph.units.slice();
    const stage = {id, type:'t', parent:graph.root.id, name:title, children:[], description:''};
    const jobs = units.splice(positions[0], positions.length, {stage});
    stage.children = jobs.map(({job}) => job.id);
    return writeUnits(definition, graph, units, nextStageId, {added:stage}) ? stage : null;
  }

  function getUngroupReason(definition, graph, stage) {
    if (!graph.valid || stage?.type !== 't' || isLoose(stage) || !graph.units.some(unit => unit.stage === stage && !unit.job)) return '해제할 단계를 확인해 주세요.';
    if (!graph.children(stage, ['j']).valid) return '단계와 하위 작업의 연결을 확인해 주세요.';
    return stageDataReason(definition, stage, graph.nodes);
  }

  function ungroupReason(definition, stageId) {
    const graph = inspect(definition);
    return getUngroupReason(definition, graph, graph.byId.get(stageId));
  }

  function ungroup(definition, stageId, nextStageId) {
    const graph = inspect(definition), stage = graph.byId.get(stageId);
    const reason = getUngroupReason(definition, graph, stage);
    if (reason) throw new Error(reason);
    const units = graph.units.slice(), index = units.findIndex(unit => unit.stage === stage);
    units.splice(index, 1, ...graph.children(stage, ['j']).ordered.map(job => ({stage, job})));
    return writeUnits(definition, graph, units, nextStageId, {removed:stage});
  }

  function move(definition, id, offset, nextStageId) {
    const graph = inspect(definition);
    if (!graph.valid || (offset !== -1 && offset !== 1)) return false;
    const index = graph.units.findIndex(unit => (unit.job || unit.stage).id === id);
    if (index >= 0) {
      const to = index + offset;
      if (to < 0 || to >= graph.units.length) return false;
      const units = graph.units.slice();
      [units[index], units[to]] = [units[to], units[index]];
      return writeUnits(definition, graph, units, nextStageId);
    }
    const job = graph.byId.get(id), stage = graph.byId.get(parentId(job));
    if (job?.type !== 'j' || stage?.type !== 't' || !graph.units.some(unit => unit.stage === stage && !unit.job)) return false;
    const {ordered, valid} = graph.children(stage, ['j']);
    const from = ordered.indexOf(job), to = from + offset;
    if (!valid || from < 0 || to < 0 || to >= ordered.length) return false;
    [ordered[from], ordered[to]] = [ordered[to], ordered[from]];
    stage.children = ordered.map(node => node.id);
    return true;
  }

  function removeEmptyLooseStages(definition) {
    const graph = inspect(definition);
    if (!graph.valid) return false;
    const empty = new Set(graph.loose.filter(stage => !stage.children?.length).map(stage => stage.id));
    if (!empty.size) return false;
    remove(definition, empty);
    graph.root.children = graph.root.children.filter(id => !empty.has(id));
    return true;
  }

  return Object.freeze({units:definition => inspect(definition).units, isLoose, addLooseJob, group, move, ungroup, ungroupReason,
    canUngroup:(definition, stageId) => !ungroupReason(definition, stageId), removeEmptyLooseStages});
}

const workTaskLayout = createWorkTaskLayout();
