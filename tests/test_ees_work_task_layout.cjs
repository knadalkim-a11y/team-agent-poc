const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../branding/ees/ui/ees-work-task-layout.js'), 'utf8');
const layout = vm.runInNewContext(source + '\nworkTaskLayout;');
const plain = value => JSON.parse(JSON.stringify(value));
const ids = (...values) => () => values.shift();
const loose = (id, children) => ({id, type:'t', name:'작업', parent:'p', children, ungrouped:true});
const named = (id, children) => ({id, type:'t', name:'확인', parent:'p', children, description:'', instructions:'', deps:[], inputs:[], mode:'human', result_block:'human_confirm', human_confirmation:true, completion:{rule:''}});
const job = (id, parent, values={}) => ({id, type:'j', name:'작업 '+id, parent, children:[], ...values});
const definition = (...nodes) => ({nodes:{p:{id:'p', type:'p', children:nodes.filter(node => node.parent === 'p').map(node => node.id)}, ...Object.fromEntries(nodes.map(node => [node.id, node]))}});
const order = value => Array.from(layout.units(value), unit => (unit.job || unit.stage).id);

test('loose jobs append after named stages with no visible container', () => {
  const value = definition(named('existing',['old']),job('old','existing'));
  const next = ids('loose-1');
  assert.equal(layout.addLooseJob(value,job('a',null,{inputs:[{id:'form'}]}),next),true);
  assert.equal(layout.addLooseJob(value,job('b',null),next),true);
  assert.deepEqual(order(value),['existing','a','b']);
  assert.deepEqual(plain(value.nodes['loose-1']),loose('loose-1',['a','b']));
  assert.equal(value.nodes.a.parent,'loose-1');
  assert.deepEqual(value.nodes.a.inputs,[{id:'form'}]);
  assert.equal(layout.isLoose({...named('actual',[]),name:'작업'}),false);
});

test('grouping a middle range keeps order, job identities and all references', () => {
  const a = job('a','loose-1'), b = job('b','loose-1',{deps:['a'],condition:{field:'line',op:'eq',value:'L1'}});
  const c = job('c','loose-1',{deps:['b'],api_binding:{inputs:{id:{run_input:'query'},page:{result:{job_id:'b',field:'id',confirmed:true}}}}});
  const d = job('d','loose-1',{deps:['c']});
  const value = definition(loose('loose-1',['a','b','c','d']),a,b,c,d,named('existing',['old']),job('old','existing',{deps:['b']}));
  const savedJobData = plain([b,c,d]);
  const result = layout.group(value,['c','b'],' 단계 이름 ',ids('new','split'));
  assert.equal(result,value.nodes.new);
  assert.equal(result.name,'단계 이름');
  assert.deepEqual(plain(result.children),['b','c']);
  assert.deepEqual(order(value),['a','new','d','existing']);
  assert.deepEqual(plain(value.nodes.p.children),['loose-1','new','split','existing']);
  assert.equal(value.nodes.b,b);assert.equal(value.nodes.c,c);assert.equal(value.nodes.d,d);
  assert.deepEqual(plain([b,c,d]).map((node,index)=>({...node,parent:savedJobData[index].parent})),savedJobData);
  assert.equal(b.parent,'new');assert.equal(c.parent,'new');assert.equal(d.parent,'split');
});

test('group selection and stage ID failures do not mutate the draft', () => {
  const value = definition(loose('loose-1',['a','b','c']),job('a','loose-1'),job('b','loose-1'),job('c','loose-1'),named('existing',['old']),job('old','existing'),loose('loose-2',['d']),job('d','loose-2'));
  const before = plain(value);
  for (const [jobs, next] of [[['a','c'], ids('new')], [['c','d'], ids('new')], [['a','a'], ids('new')], [['old'], ids('new')], [['b'], ids('new','new')], [['a'], ids('existing')]]) {
    assert.equal(layout.group(value,jobs,'수정',next),null);
    assert.deepEqual(value,before);
  }
  const twoBlocks = definition(loose('loose-1',['a','b']),job('a','loose-1'),job('b','loose-1'),named('existing',['old']),job('old','existing'));
  const original = plain(twoBlocks);
  assert.equal(layout.move(twoBlocks,'existing',-1,ids('existing')),false);
  assert.deepEqual(twoBlocks,original);
});

test('ungrouping a legacy plain stage places its jobs between both neighbors', () => {
  const a = job('a','left'), b = job('b','plain',{deps:['a']}), c = job('c','plain',{deps:['b']}), d = job('d','right',{deps:['c']});
  const value = definition(loose('left',['a']),a,named('plain',['b','c']),b,c,loose('right',['d']),d);
  assert.equal(layout.canUngroup(value,'plain'),true);
  assert.equal(layout.ungroup(value,'plain',ids()),true);
  assert.deepEqual(order(value),['a','b','c','d']);
  assert.deepEqual(Object.keys(value.nodes),['p','left','a','b','c','d']);
  assert.equal(value.nodes.b,b);assert.equal(value.nodes.c,c);
  assert.equal(b.parent,'left');assert.equal(c.parent,'left');assert.equal(d.parent,'left');
  assert.deepEqual([b.deps,c.deps,d.deps],[['a'],['b'],['c']]);
});

test('ungrouping stops before dropping inherited settings, deadlines, overrides or inbound references', () => {
  const cases = [
    [/설명/, value => value.nodes.stage.description = '실행 의미가 있는 설명'],
    [/추가 설정/, value => value.nodes.stage.inputs = [{id:'target'}]],
    [/추가 설정/, value => value.nodes.stage.condition = {field:'line',op:'eq',value:'L1'}],
    [/추가 설정/, value => value.nodes.stage.assignee = {kind:'group',id:'reviewers'}],
    [/추가 설정/, value => value.nodes.stage.access_groups = []],
    [/추가 설정/, value => value.nodes.stage.deps = ['b']],
    [/추가 설정/, value => value.nodes.stage.enabled = false],
    [/기한/, value => value.schedule = {stage_deadlines:{stage:{due:2}}}],
    [/공장별 설정/, value => value.factory_overrides = {stage:{fab:{}}}],
    [/참조/, value => value.nodes.b.deps = ['stage']],
    [/참조/, value => value.nodes.b.effect_criterion = {job_id:'stage'}],
    [/참조/, value => value.nodes.b.api_binding = {inputs:{x:{result:{job_id:'stage'}}}}],
  ];
  for (const [expected, apply] of cases) {
    const value = definition(named('stage',['a']),job('a','stage'),loose('loose-1',['b']),job('b','loose-1'));
    apply(value);
    const before = plain(value);
    assert.match(layout.ungroupReason(value,'stage'),expected);
    assert.equal(layout.canUngroup(value,'stage'),false);
    assert.throws(() => layout.ungroup(value,'stage',ids('new')),expected);
    assert.deepEqual(value,before);
  }
});

test('moving top-level blocks and local jobs changes only their authored order', () => {
  const value = definition(loose('loose-1',['a','b']),job('a','loose-1'),job('b','loose-1',{deps:['a']}),named('stage',['x','y']),job('x','stage'),job('y','stage',{deps:['x']}));
  assert.equal(layout.move(value,'b',-1,ids()),true);
  assert.deepEqual(order(value),['b','a','stage']);
  assert.equal(layout.move(value,'stage',-1,ids('split')),true);
  assert.deepEqual(order(value),['b','stage','a']);
  assert.equal(value.nodes.a.parent,'split');
  assert.equal(layout.move(value,'y',-1,ids()),true);
  assert.deepEqual(plain(value.nodes.stage.children),['y','x']);
  assert.deepEqual([value.nodes.b.deps,value.nodes.y.deps],[['a'],['x']]);
  assert.equal(layout.move(value,'b',-1,ids()),false);
});

test('removing empty generated entries preserves titled or referenced stages', () => {
  const value = definition(loose('empty',[]),loose('configured',[]),loose('referenced',[]),{...named('named',[]),name:'작업'},named('other',['a']),job('a','other',{deps:['referenced']}));
  value.nodes.configured.instructions = '기존 지침';
  assert.equal(layout.removeEmptyLooseStages(value),true);
  assert.deepEqual(value.nodes.p.children,['configured','referenced','named','other']);
  assert.equal(value.nodes.empty,undefined);
  assert.equal(value.nodes.configured.instructions,'기존 지침');
  assert.deepEqual(order(value),['configured','referenced','named','other']);
});

test('legacy array storage and direct-root jobs remain readable and repairable', () => {
  const root = {type:'p',id:'p',children:['old']};
  const old = {type:'j',id:'old',parent_id:'p',children:[],deps:[]};
  const value = {nodes:[root,old]};
  assert.deepEqual(order(value),['old']);
  assert.equal(layout.units(value)[0].stage,null);
  assert.equal(layout.group(value,['old'],'복구된 단계',ids('repair')).id,'repair');
  assert.deepEqual(value.nodes.map(node=>node.id),['p','old','repair']);
  assert.equal(value.nodes[1],old);
  assert.equal(old.parent,'repair');assert.equal(old.parent_id,'repair');
});

test('broken legacy child links render available rows without risking a destructive edit', () => {
  const value = definition(loose('loose-1',['a','missing']),job('a','loose-1'));
  const before = plain(value);
  assert.deepEqual(order(value),['a']);
  assert.equal(layout.addLooseJob(value,job('new',null),ids('loose-2')),false);
  assert.equal(layout.group(value,['a'],'새 단계',ids('named')),null);
  assert.deepEqual(value,before);
});
