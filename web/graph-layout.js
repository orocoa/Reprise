/*
 * Reprise Git graph layout prototype, 2026-10-09.
 * Browser: window.RepriseGraph.layout(commits, options)
 * Node:    const { layout } = require('./graph-layout.js')
 *
 * Input: [{ id: String, parents: String[], order?: finite Number }]
 * Options: { mainTip?: String, mainRef?: String, refs?: [{name, tip, kind?}] }
 * Greater `order` is preferred first, subject to topology. Equal/missing order
 * uses natural descending ID order, not input-array order. IDs are not dates.
 *
 * Coordinates are logical units: x = column, y = topological row. Scale x/y
 * separately when rendering. Edge points are orthogonal route guides, suitable
 * for a rounded polyline. A crossing without a commit node is not a junction.
 *
 * A route is a layout first-parent chain, NOT a Git branch identity. This
 * prototype is deterministic for a fixed graph; adding history can change its
 * columns, route heads and color indexes. It does not claim a minimum-width
 * layout or stable colors across changing repository snapshots.
 */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.RepriseGraph = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  class GraphLayoutError extends Error {
    constructor(code, message, details) {
      super(message);
      this.name = 'GraphLayoutError';
      this.code = code;
      this.details = details || {};
    }
  }

  function naturalCompare(a, b) {
    const aa = a.match(/\d+|\D+/g) || [], bb = b.match(/\d+|\D+/g) || [];
    for (let i = 0; i < Math.min(aa.length, bb.length); i += 1) {
      if (aa[i] === bb[i]) continue;
      if (/^\d+$/.test(aa[i]) && /^\d+$/.test(bb[i])) {
        const x = aa[i].replace(/^0+(?=\d)/, ''), y = bb[i].replace(/^0+(?=\d)/, '');
        if (x.length !== y.length) return x.length - y.length;
        if (x !== y) return x < y ? -1 : 1;
      }
      return aa[i] < bb[i] ? -1 : 1;
    }
    return aa.length - bb.length || (a < b ? -1 : a > b ? 1 : 0);
  }

  function layout(input, options) {
    options = options || {};
    if (!Array.isArray(input)) throw new GraphLayoutError('INVALID_INPUT', 'commits must be an array');
    const commits = new Map(), diagnostics = [];
    input.forEach(function (source) {
      if (!source || typeof source.id !== 'string' || !source.id.length) {
        throw new GraphLayoutError('INVALID_ID', 'Each commit needs a non-empty string id');
      }
      if (commits.has(source.id)) throw new GraphLayoutError('DUPLICATE_ID', 'Duplicate commit id: ' + source.id);
      const parents = source.parents === undefined ? [] : source.parents;
      if (!Array.isArray(parents) || parents.some(p => typeof p !== 'string' || !p.length)) {
        throw new GraphLayoutError('INVALID_PARENTS', 'parents must contain non-empty string ids', {id: source.id});
      }
      if (new Set(parents).size !== parents.length) {
        throw new GraphLayoutError('DUPLICATE_PARENT', 'A parent is repeated', {id: source.id});
      }
      if (source.order !== undefined && (typeof source.order !== 'number' || !Number.isFinite(source.order))) {
        throw new GraphLayoutError('INVALID_ORDER', 'order must be a finite number', {id: source.id});
      }
      commits.set(source.id, {id: source.id, parents: parents.slice(), order: source.order});
    });

    const refs = (options.refs || []).map(function (ref) {
      if (!ref || typeof ref.name !== 'string' || typeof ref.tip !== 'string') {
        throw new GraphLayoutError('INVALID_REF', 'refs need name and tip strings');
      }
      return {name: ref.name, tip: ref.tip, kind: ref.kind || 'ref'};
    }).sort((a, b) => naturalCompare(a.name, b.name) || naturalCompare(a.tip, b.tip));

    let mainTip = options.mainTip === undefined ? null : options.mainTip;
    if (mainTip !== null && typeof mainTip !== 'string') {
      throw new GraphLayoutError('INVALID_MAIN_TIP', 'mainTip must be a string');
    }
    if (mainTip === null && options.mainRef !== undefined) {
      const matching = refs.filter(ref => ref.name === options.mainRef);
      if (matching.length === 1) mainTip = matching[0].tip;
      else diagnostics.push({code: 'UNRESOLVED_MAIN_REF', ref: options.mainRef});
    }

    const childIds = new Map(), firstParentChildIds = new Map(), remainingChildren = new Map();
    commits.forEach(c => { childIds.set(c.id, []); firstParentChildIds.set(c.id, []); remainingChildren.set(c.id, 0); });
    const missingChildren = new Map();
    commits.forEach(function (child) {
      child.parents.forEach(function (parentId, parentIndex) {
        if (commits.has(parentId)) {
          childIds.get(parentId).push(child.id);
          if (parentIndex === 0) firstParentChildIds.get(parentId).push(child.id);
          remainingChildren.set(parentId, remainingChildren.get(parentId) + 1);
        } else {
          if (!missingChildren.has(parentId)) missingChildren.set(parentId, []);
          missingChildren.get(parentId).push(child.id);
        }
      });
    });
    const compare = function (a, b) {
      const x = commits.get(a), y = commits.get(b);
      // Explicit ordering sorts ahead of unspecified ordering; topology still wins.
      if (x.order !== undefined || y.order !== undefined) {
        if (x.order === undefined) return 1;
        if (y.order === undefined) return -1;
        if (x.order !== y.order) return y.order - x.order;
      }
      return -naturalCompare(a, b);
    };
    childIds.forEach(ids => ids.sort(compare));
    firstParentChildIds.forEach(ids => ids.sort(compare));
    missingChildren.forEach(ids => ids.sort(compare));
    const ready = Array.from(commits.keys()).filter(id => remainingChildren.get(id) === 0).sort(compare);
    const ordered = [];
    while (ready.length) {
      const id = ready.shift();
      ordered.push(id);
      commits.get(id).parents.forEach(function (parentId) {
        if (!commits.has(parentId)) return;
        remainingChildren.set(parentId, remainingChildren.get(parentId) - 1);
        if (remainingChildren.get(parentId) === 0) { ready.push(parentId); ready.sort(compare); }
      });
    }
    if (ordered.length !== commits.size) {
      throw new GraphLayoutError('CYCLE', 'Commit relations contain a cycle', {
        unresolvedIds: Array.from(commits.keys()).filter(id => !ordered.includes(id)).sort(naturalCompare)
      });
    }
    const rowById = new Map(ordered.map((id, row) => [id, row]));

    const mainPath = [];
    let mainBoundary = null;
    if (mainTip !== null) {
      if (!commits.has(mainTip)) diagnostics.push({code: 'UNKNOWN_MAIN_TIP', id: mainTip});
      else {
        let cursor = mainTip;
        while (cursor && commits.has(cursor)) {
          mainPath.push(cursor);
          cursor = commits.get(cursor).parents[0];
        }
        if (cursor) mainBoundary = cursor;
      }
    }
    const mainSet = new Set(mainPath), routes = [], routeForId = new Map();
    function addRoute(ids, isMain) {
      const tail = commits.get(ids[ids.length - 1]), parentId = tail.parents[0] || null;
      const route = {
        id: isMain ? 'main' : 'route:' + ids[0],
        headId: ids[0], nodeIds: ids.slice(), isMain: isMain,
        startRow: rowById.get(ids[0]),
        endRow: parentId ? (rowById.has(parentId) ? rowById.get(parentId) : ordered.length) : rowById.get(tail.id),
        terminal: parentId ? {kind: commits.has(parentId) ? 'known-parent' : 'missing-parent', parentId: parentId} : {kind: 'root'},
        lane: null, colorIndex: null
      };
      routes.push(route);
      ids.forEach(id => routeForId.set(id, route));
      return route;
    }
    if (mainPath.length) addRoute(mainPath, true);
    ordered.forEach(function (head) {
      if (routeForId.has(head)) return;
      const ids = [];
      let cursor = head;
      while (cursor && commits.has(cursor) && !routeForId.has(cursor)) {
        ids.push(cursor);
        cursor = commits.get(cursor).parents[0];
      }
      addRoute(ids, false);
    });

    const occupied = new Map();
    const mainRoute = routes.find(route => route.isMain);
    if (mainRoute) { mainRoute.lane = 0; mainRoute.colorIndex = 0; occupied.set(0, [{start: -1, end: ordered.length}]); }
    let colorIndex = 1;
    routes.filter(route => !route.isMain).sort((a, b) => a.startRow - b.startRow || naturalCompare(a.id, b.id)).forEach(function (route) {
      let lane = mainRoute ? 1 : 0;
      while ((occupied.get(lane) || []).some(span => span.start <= route.endRow && route.startRow <= span.end)) lane += 1;
      route.lane = lane;
      route.colorIndex = colorIndex++;
      if (!occupied.has(lane)) occupied.set(lane, []);
      occupied.get(lane).push({start: route.startRow, end: route.endRow});
    });

    const rows = ordered.map(function (id, row) {
      const commit = commits.get(id), route = routeForId.get(id);
      return {
        id: id, row: row, lane: route.lane, routeId: route.id, colorIndex: route.colorIndex,
        isMain: mainSet.has(id), isMerge: commit.parents.length > 1,
        parents: commit.parents.slice(), childIds: childIds.get(id).slice(),
        firstParentChildIds: firstParentChildIds.get(id).slice(),
        refs: refs.filter(ref => ref.tip === id), order: commit.order === undefined ? null : commit.order
      };
    });
    const nodes = new Map(rows.map(node => [node.id, node]));
    const boundaries = [];
    let nextBoundaryLane = Math.max(-1, ...rows.map(node => node.lane)) + 1;
    Array.from(missingChildren.keys()).sort(naturalCompare).forEach(function (id) {
      const ids = missingChildren.get(id), firstParentChild = ids.find(childId => commits.get(childId).parents[0] === id);
      // Keep an unknown first parent on its established route if that lane is free.
      const preferredLane = id === mainBoundary ? 0 : firstParentChild ? nodes.get(firstParentChild).lane : nextBoundaryLane;
      const lane = boundaries.some(boundary => boundary.lane === preferredLane) ? nextBoundaryLane : preferredLane;
      nextBoundaryLane = Math.max(nextBoundaryLane, lane + 1);
      boundaries.push({id: id, row: ordered.length, lane: lane, kind: 'missing-parent', childIds: ids.slice()});
      diagnostics.push({code: 'MISSING_PARENT', id: id, childIds: ids.slice()});
    });
    const boundaryById = new Map(boundaries.map(boundary => [boundary.id, boundary]));
    refs.filter(ref => !commits.has(ref.tip)).forEach(ref => diagnostics.push({code: 'REF_OUTSIDE_GRAPH', name: ref.name, tip: ref.tip}));

    const edgeSpecs = [];
    rows.forEach(function (child) {
      child.parents.forEach(function (parentId, parentIndex) {
        edgeSpecs.push({child: child, parent: nodes.get(parentId) || boundaryById.get(parentId), parentIndex: parentIndex});
      });
    });
    // Protect ordinary first-parent chains before routing extra merge-parent edges.
    edgeSpecs.sort((a, b) => Number(a.parentIndex > 0) - Number(b.parentIndex > 0) || a.child.row - b.child.row || a.parentIndex - b.parentIndex);
    const reservedRails = new Map(), edges = [];
    function blocked(rail, child, parent, from, to) {
      if (rows.some(node => node.lane === rail && node.id !== child.id && node.id !== parent.id && node.row > child.row && node.row < parent.row)) return true;
      return (reservedRails.get(rail) || []).some(span => Math.max(from, span.from) < Math.min(to, span.to));
    }
    edgeSpecs.forEach(function (spec) {
      const child = spec.child, parent = spec.parent;
      const missing = !nodes.has(parent.id), preferredRail = spec.parentIndex === 0 ? child.lane : parent.lane;
      const from = child.row + 0.28, to = parent.row - 0.28;
      let rail = preferredRail;
      if (blocked(rail, child, parent, from, to)) {
        rail = Math.max(child.lane, parent.lane) + 1;
        while (blocked(rail, child, parent, from, to)) rail += 1;
      }
      if (!reservedRails.has(rail)) reservedRails.set(rail, []);
      reservedRails.get(rail).push({from: from, to: to});
      const guides = [
        {x: child.lane, y: child.row}, {x: child.lane, y: from},
        {x: rail, y: from}, {x: rail, y: to},
        {x: parent.lane, y: to}, {x: parent.lane, y: parent.row}
      ];
      const points = guides.filter((point, index) => !index || point.x !== guides[index - 1].x || point.y !== guides[index - 1].y);
      const route = spec.parentIndex > 0 && !missing ? routeForId.get(parent.id) : routeForId.get(child.id);
      edges.push({
        id: child.id + '>' + parent.id, childId: child.id, parentId: parent.id,
        parentIndex: spec.parentIndex, relation: spec.parentIndex === 0 ? 'first-parent' : 'additional-parent',
        kind: missing ? 'boundary' : spec.parentIndex > 0 ? 'merge' : child.isMain && mainSet.has(parent.id) ? 'main' : 'branch',
        routeId: route.id, colorIndex: route.colorIndex, rail: rail, preferredRail: preferredRail,
        usesBypass: rail !== preferredRail, missingParent: missing, points: points
      });
    });
    edges.sort((a, b) => rowById.get(a.childId) - rowById.get(b.childId) || a.parentIndex - b.parentIndex);
    const laneCount = Math.max(-1, ...rows.map(node => node.lane), ...boundaries.map(node => node.lane), ...edges.map(edge => edge.rail)) + 1;
    return {
      version: 1, rows: rows, edges: edges, boundaries: boundaries,
      mainTip: mainTip, mainPath: mainPath, mainBoundary: mainBoundary,
      routes: routes, refs: refs, laneCount: laneCount,
      rowCount: rows.length + (boundaries.length ? 1 : 0), diagnostics: diagnostics,
      semantics: {
        rowOrder: 'children-before-parents', mainPath: 'explicit-tip-first-parent-chain',
        routeIdentity: 'layout-chain-not-git-branch', crossing: 'no-junction-without-commit-node',
        boundary: 'known-parent-id-with-unavailable-commit', stability: 'deterministic-for-fixed-input-graph'
      }
    };
  }

  return {layout: layout, GraphLayoutError: GraphLayoutError};
});
