'use strict';
const assert = require('node:assert/strict');
const {test} = require('node:test');
const {layout, GraphLayoutError} = require('../web/graph-layout.js');

const commit = (id, parents = [], order) => order === undefined ? {id, parents} : {id, parents, order};
const current = [
  commit('28', ['27']), commit('27', ['26']), commit('26', ['25', '25A']),
  commit('25B', ['25A']), commit('25A', ['25']), commit('25', ['24']),
  commit('24T', ['24']), commit('24', ['23']), commit('23', ['22']), commit('22')
];

const {verifyGraph} = require('./graph-contract.cjs');

test('linear history uses one main rail', () => {
  const source = [commit('3', ['2']), commit('2', ['1']), commit('1')];
  const graph = layout(source, {mainTip: '3'});
  verifyGraph(source, graph);
  assert.deepEqual(graph.mainPath, ['3', '2', '1']);
  assert.equal(graph.laneCount, 1);
  assert.ok(graph.rows.every(row => row.isMain && row.lane === 0));
});

test('a fork retains an open branch tip and does not invent a merge', () => {
  const source = [commit('4', ['2']), commit('3', ['2']), commit('2', ['1']), commit('1')];
  const graph = layout(source, {mainTip: '4'});
  verifyGraph(source, graph);
  assert.equal(graph.edges.filter(edge => edge.kind === 'merge').length, 0);
  assert.notEqual(graph.rows.find(row => row.id === '3').lane, 0);
  assert.deepEqual(graph.rows.find(row => row.id === '2').childIds, ['4', '3']);
  assert.deepEqual(graph.mainPath, ['4', '2', '1']);
});

test('a merge has one first-parent continuation and an explicit additional parent', () => {
  const source = [commit('4', ['2', '3']), commit('3', ['2']), commit('2', ['1']), commit('1')];
  const graph = layout(source, {mainTip: '4'});
  verifyGraph(source, graph);
  assert.deepEqual(graph.mainPath, ['4', '2', '1']);
  assert.equal(graph.edges.find(edge => edge.id === '4>3').relation, 'additional-parent');
  assert.equal(graph.edges.find(edge => edge.id === '4>3').kind, 'merge');
  assert.equal(graph.rows.find(row => row.id === '4').isMerge, true);
  assert.equal(graph.rows.find(row => row.id === '3').isMain, false);
});

test('merge targets an earlier branch commit and bypasses its unmerged descendant', () => {
  const graph = layout(current, {mainTip: '28'});
  verifyGraph(current, graph);
  assert.deepEqual(graph.rows.map(row => row.id), ['28', '27', '26', '25B', '25A', '25', '24T', '24', '23', '22']);
  const merge = graph.edges.find(edge => edge.id === '26>25A');
  const branchTip = graph.rows.find(row => row.id === '25B');
  assert.equal(merge.usesBypass, true);
  assert.notEqual(merge.rail, branchTip.lane);
  assert.equal(graph.edges.some(edge => edge.kind === 'merge' && ['25B', '24T'].includes(edge.parentId)), false);
  assert.equal(graph.rows.find(row => row.id === '24T').childIds.length, 0);
  assert.equal(branchTip.childIds.length, 0);
});

test('octopus merge preserves all three ordered parents', () => {
  const source = [commit('5', ['2', '4', '3']), commit('4', ['1']), commit('3', ['1']), commit('2', ['1']), commit('1')];
  const graph = layout(source, {mainTip: '5'});
  verifyGraph(source, graph);
  assert.deepEqual(graph.edges.filter(edge => edge.childId === '5').map(edge => [edge.parentId, edge.parentIndex]), [['2', 0], ['4', 1], ['3', 2]]);
  assert.deepEqual(graph.mainPath, ['5', '2', '1']);
});

test('missing parents become marked boundaries, never substitute commits', () => {
  const source = [commit('5', ['4', 'external']), commit('4', ['3']), commit('2', ['external'])];
  const graph = layout(source, {mainTip: '5'});
  verifyGraph(source, graph);
  assert.deepEqual(graph.mainPath, ['5', '4']);
  assert.equal(graph.mainBoundary, '3');
  assert.deepEqual(graph.boundaries.map(boundary => boundary.id), ['3', 'external']);
  assert.equal(graph.rows.some(row => row.id === 'external'), false);
  assert.equal(graph.diagnostics.filter(d => d.code === 'MISSING_PARENT').length, 2);
  assert.equal(graph.edges.filter(edge => edge.parentId === 'external').length, 2);
});

test('main line requires an explicit tip or explicitly selected ref', () => {
  const refs = [{name: 'main', tip: '28'}, {name: 'feature', tip: '25B'}];
  const noSelection = layout(current, {refs});
  assert.deepEqual(noSelection.mainPath, []);
  assert.ok(noSelection.rows.every(row => !row.isMain));
  assert.deepEqual(layout(current, {refs, mainRef: 'main'}).mainPath, ['28', '27', '26', '25', '24', '23', '22']);
  const unknown = layout(current, {mainTip: 'unavailable'});
  assert.deepEqual(unknown.mainPath, []);
  assert.ok(unknown.diagnostics.some(d => d.code === 'UNKNOWN_MAIN_TIP'));
});

test('row-order hints cannot override ancestry', () => {
  const source = [commit('child', ['parent'], -10), commit('parent', [], 100), commit('peer', [], 0)];
  const graph = layout(source, {mainTip: 'child'});
  verifyGraph(source, graph);
  assert.deepEqual(graph.rows.map(row => row.id), ['peer', 'child', 'parent']);
});

test('input order does not alter topology, routes, rails, or colors', () => {
  const baseline = layout(current, {mainTip: '28'});
  let seed = 1729;
  const random = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; };
  for (let trial = 0; trial < 100; trial += 1) {
    const shuffled = current.slice();
    for (let i = shuffled.length - 1; i > 0; i -= 1) {
      const j = Math.floor(random() * (i + 1));
      [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
    }
    assert.deepEqual(layout(shuffled, {mainTip: '28'}), baseline);
  }
});

test('seeded DAG fixtures have exact edges and no unrelated-node collisions', () => {
  let seed = 402;
  const random = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; };
  for (let trial = 0; trial < 30; trial += 1) {
    const source = [commit('c0')];
    for (let i = 1; i < 35; i += 1) {
      const parentIndexes = new Set([Math.floor(random() * i)]);
      if (random() > 0.7) parentIndexes.add(Math.floor(random() * i));
      if (random() > 0.92) parentIndexes.add(Math.floor(random() * i));
      source.push(commit('c' + i, Array.from(parentIndexes, index => 'c' + index)));
    }
    verifyGraph(source, layout(source, {mainTip: 'c34'}));
  }
});

test('shared columns remain layout positions, with distinct route identities', () => {
  const graph = layout(current, {mainTip: '28'});
  const blue = graph.rows.find(row => row.id === '25B'), green = graph.rows.find(row => row.id === '24T');
  assert.equal(blue.lane, green.lane, 'non-overlapping routes may reuse a column');
  assert.notEqual(blue.routeId, green.routeId);
  assert.notEqual(blue.colorIndex, green.colorIndex);
});

test('invalid input and cyclic graphs fail explicitly', () => {
  assert.throws(() => layout([commit('a', ['b']), commit('b', ['a'])]), error => error instanceof GraphLayoutError && error.code === 'CYCLE');
  assert.throws(() => layout([commit('a'), commit('a')]), error => error.code === 'DUPLICATE_ID');
  assert.throws(() => layout([commit('a', ['b', 'b'])]), error => error.code === 'DUPLICATE_PARENT');
  assert.throws(() => layout([commit('a', [], NaN)]), error => error.code === 'INVALID_ORDER');
});

test('empty graph is valid and all input data remain unchanged', () => {
  assert.equal(layout([]).laneCount, 0);
  const before = JSON.stringify(current);
  layout(current, {mainTip: '28'});
  assert.equal(JSON.stringify(current), before);
});

test('ref aliases, renames, and deletion cannot manufacture or remove parent edges', () => {
  const refs = [{name: 'refs/heads/trunk', tip: '28'}, {name: 'refs/tags/release', tip: '28'}, {name: 'refs/heads/实验', tip: '25B'}];
  const baseline = layout(current, {mainTip: '28', refs});
  assert.equal(baseline.rows.filter(n => n.id === '28').length, 1);
  assert.equal(baseline.rows.find(n => n.id === '28').refs.length, 2);
  const renamed = layout(current, {mainTip: '28', refs: [{name: 'refs/heads/renamed', tip: '28'}]});
  assert.deepEqual(renamed.edges, baseline.edges);
  assert.deepEqual(renamed.routes, baseline.routes);
});

test('unrelated roots stay separate, even with identical sorting hints', () => {
  const source = [commit('a2', ['a1'], 1), commit('a1', [], 1), commit('b2', ['b1'], 1), commit('b1', [], 1)];
  const graph = layout(source, {mainTip: 'a2'});
  verifyGraph(source, graph);
  assert.equal(graph.edges.length, 2);
  assert.ok(graph.edges.every(e => e.childId[0] === e.parentId[0]));
});

test('wide histories allocate additional lanes rather than crossing unrelated nodes', () => {
  const source = [commit('root')];
  for (let i = 0; i < 16; i++) source.push(commit('branch' + i, ['root']));
  source.push(commit('merge', source.slice(1).map(c => c.id)));
  const graph = layout(source, {mainTip: 'merge'});
  verifyGraph(source, graph);
  assert.ok(graph.laneCount >= 16);
  assert.equal(graph.edges.filter(e => e.childId === 'merge').length, 16);
});

test('full SHA-1 and SHA-256 identities remain distinct with a shared short prefix', () => {
  for (const size of [40, 64]) {
    const first = 'abcdef0' + '1'.repeat(size - 7), second = 'abcdef0' + '2'.repeat(size - 7);
    const source = [commit(second, [first]), commit(first)];
    const graph = layout(source, {mainTip: second});
    verifyGraph(source, graph);
    assert.equal(graph.rows.length, 2);
  }
});

test('boundary diagnostics and external refs do not add synthetic commit nodes', () => {
  const source = [commit('tip', ['unloaded'])];
  const graph = layout(source, {mainTip: 'tip', refs: [{name: 'refs/heads/outside', tip: 'elsewhere'}]});
  verifyGraph(source, graph);
  assert.equal(graph.edges[0].missingParent, true);
  assert.equal(graph.rows.length, 1);
  assert.ok(graph.diagnostics.some(d => d.code === 'REF_OUTSIDE_GRAPH'));
});
