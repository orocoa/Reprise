'use strict';
const assert = require('node:assert/strict');
const {layout} = require('../web/graph-layout.js');

function verifyGraph(source, graph) {
  const rows = new Map(graph.rows.map(row => [row.id, row]));
  const expected = source.flatMap(c => c.parents.map((p, index) => `${c.id}>${p}:${index}`)).sort();
  const actual = graph.edges.map(e => `${e.childId}>${e.parentId}:${e.parentIndex}`).sort();
  assert.deepEqual(actual, expected, 'The layout must preserve every edge and invent none');
  assert.equal(graph.rows.length, source.length);
  assert.equal(rows.size, source.length, 'Each commit has exactly one node');
  for (const commit of source) assert.deepEqual(rows.get(commit.id).parents, commit.parents, 'Parent order is immutable');
  const missing = [...new Set(source.flatMap(c => c.parents).filter(id => !rows.has(id)))].sort();
  assert.deepEqual(graph.boundaries.map(b => b.id).sort(), missing, 'Every missing parent has a distinct boundary');
  assert.equal(new Set(graph.boundaries.map(b => b.lane)).size, graph.boundaries.length);
  const main = [];
  let cursor = graph.mainTip;
  while (rows.has(cursor)) { main.push(cursor); cursor = rows.get(cursor).parents[0]; }
  assert.deepEqual(graph.mainPath, main, 'Main is exactly the selected first-parent chain');
  assert.deepEqual(graph.rows.filter(n => n.isMain).map(n => n.id), main);
  assert.ok(graph.rows.filter(n => n.isMain).every(n => n.lane === 0));
  for (const route of graph.routes) {
    for (const peer of graph.routes) {
      if (route.id === peer.id || route.lane !== peer.lane) continue;
      assert.ok(route.endRow < peer.startRow || peer.endRow < route.startRow, 'Shared columns require disjoint closed lifetimes');
    }
  }
  graph.edges.forEach(function (edge) {
    const child = rows.get(edge.childId);
    const parent = rows.get(edge.parentId) || graph.boundaries.find(b => b.id === edge.parentId);
    assert.ok(child.row < parent.row, 'Parents must be below children');
    assert.deepEqual(edge.points[0], {x: child.lane, y: child.row});
    assert.deepEqual(edge.points[edge.points.length - 1], {x: parent.lane, y: parent.row});
    for (let i = 1; i < edge.points.length; i += 1) {
      const a = edge.points[i - 1], b = edge.points[i];
      assert.ok(a.x === b.x || a.y === b.y, 'Guides must be orthogonal');
      rows.forEach(function (node) {
        if (node.id === edge.childId || node.id === edge.parentId) return;
        const onVertical = a.x === b.x && node.lane === a.x && node.row >= Math.min(a.y, b.y) && node.row <= Math.max(a.y, b.y);
        const onHorizontal = a.y === b.y && node.row === a.y && node.lane >= Math.min(a.x, b.x) && node.lane <= Math.max(a.x, b.x);
        assert.ok(!onVertical && !onHorizontal, `${edge.id} must not run through unrelated ${node.id}`);
      });
    }
  });
  assert.deepEqual(JSON.parse(JSON.stringify(graph)), graph, 'Output must be plain JSON data');
}

module.exports = {verifyGraph};
if (require.main === module) {
  const input = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
  const graph = layout(input.commits, input.options);
  verifyGraph(input.commits, graph);
  process.stdout.write(JSON.stringify(graph));
}
