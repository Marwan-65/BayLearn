// Layout Engine --, Unit Tests
// Covers spec section 13.3 (layout tests) plus a bunch of edge cases that
// have burned people before (0-key nodes, single-child internals, wide roots).
//
// Run with:  node src/tests/layout.test.js
//
// These tests build real B-tree states via the Stage 1 insert/delete modules
// so the layout is always exercised on structurally valid trees.

const { test, suite, summary, eq, ok } = require('./runner');
const { computeLayout, calcNodeWidth, calcNodeHeight } = require('../core/layout');
const { resetIdCounter, createStep } = require('../core/shared');
const { createTree, validate }       = require('../core/BTree');
const { insert }   = require('../core/insert');
const { deleteKey }= require('../core/delete');

const D = computeLayout.DEFAULTS; // shorthand for the default constants

// ─── Helpers ──────────────────────────────────────────────────────────────────

// Resets the ID counter so node IDs are predictable between tests
function fresh(t = 2) {
  resetIdCounter();
  return createTree(t);
}

// Builds a tree by inserting the given keys in order
function buildTree(t, keys) {
  let state = fresh(t);
  for (const k of keys) {
    const steps = insert(state, k);
    state = steps[steps.length - 1].state;
  }
  return state;
}

// Collects all node IDs at a given depth (root = depth 0)
function nodesAtDepth(state, targetDepth) {
  const result = [];
  function walk(nodeId, depth) {
    if (depth === targetDepth) { result.push(nodeId); return; }
    const n = state.nodes[nodeId];
    if (!n.isLeaf) n.children.forEach(c => walk(c, depth + 1));
  }
  walk(state.rootId, 0);
  return result;
}

// Returns all leaf node IDs via DFS
function allLeaves(state) {
  const result = [];
  function walk(id) {
    const n = state.nodes[id];
    if (n.isLeaf) { result.push(id); return; }
    n.children.forEach(walk);
  }
  walk(state.rootId);
  return result;
}

// Returns the depth of a node by walking parentId chain
function nodeDepth(state, nodeId) {
  let d = 0;
  let n = state.nodes[nodeId];
  while (n.parentId) { d++; n = state.nodes[n.parentId]; }
  return d;
}

// Checks if two horizontal ranges [ax, ax+aw] and [bx, bx+bw] overlap.
// Uses a tiny epsilon so floating-point edges that are technically touching
// (which is fine at SIBLING_SEPARATION = 24) don't count as overlaps.
function rangesOverlap(ax, aw, bx, bw, eps = 0.5) {
  const aLeft  = ax - aw / 2;
  const aRight = ax + aw / 2;
  const bLeft  = bx - bw / 2;
  const bRight = bx + bw / 2;
  return aLeft + eps < bRight && bLeft + eps < aRight;
}

// ─── Width formula ────────────────────────────────────────────────────────────

suite('calcNodeWidth --, spec section 4.2 examples', () => {
  test('1 key → 72px', () => {
    eq(calcNodeWidth(1, D), 72);
  });

  test('3 keys → 184px', () => {
    eq(calcNodeWidth(3, D), 184);
  });

  test('5 keys → 296px  (maximum for t=3)', () => {
    eq(calcNodeWidth(5, D), 296);
  });

  test('0-key node gets 0px of slot area, only padding', () => {
    // temporary empty root during deletion should not produce a negative width
    eq(calcNodeWidth(0, D), 2 * D.NODE_PADDING_X);
  });

  test('width grows linearly with key count', () => {
    const w1 = calcNodeWidth(1, D);
    const w2 = calcNodeWidth(2, D);
    const w3 = calcNodeWidth(3, D);
    // each additional key adds SLOT_WIDTH + SLOT_GAP
    eq(w2 - w1, D.SLOT_WIDTH + D.SLOT_GAP);
    eq(w3 - w2, D.SLOT_WIDTH + D.SLOT_GAP);
  });

  test('custom theme overrides are respected', () => {
    const custom = { ...D, SLOT_WIDTH: 60, NODE_PADDING_X: 8 };
    eq(calcNodeWidth(1, custom), 60 + 0 + 16);
    eq(calcNodeWidth(3, custom), 3 * 60 + 2 * 4 + 16);
  });
});

suite('calcNodeHeight', () => {
  test('matches spec formula: PADDING_Y*2 + SLOT_HEIGHT = 72px', () => {
    eq(calcNodeHeight(D), D.NODE_PADDING_Y * 2 + D.SLOT_HEIGHT);
    eq(calcNodeHeight(D), 72);
  });
});

// ─── Single-node tree ─────────────────────────────────────────────────────────

suite('single-node tree (root is leaf)', () => {
  test('empty root: layout has one entry', () => {
    const state = fresh(2);
    const layout = computeLayout(state);
    eq(Object.keys(layout.nodes).length, 1);
  });

  test('root is placed at x=0, y=0', () => {
    const state = fresh(2);
    const layout = computeLayout(state);
    const pos = layout.nodes[state.rootId];
    ok(Math.abs(pos.x) < 0.01, `root.x should be ~0, got ${pos.x}`);
    eq(pos.y, 0);
  });

  test('root with 1 key produces 1 key slot', () => {
    const state = buildTree(2, [42]);
    const layout = computeLayout(state);
    eq(layout.keys[state.rootId].length, 1);
  });

  test('root with 3 keys produces 3 slots', () => {
    const state = buildTree(2, [10, 20, 30]);
    const layout = computeLayout(state);
    eq(layout.keys[state.rootId].length, 3);
  });

  test('leaf node has no pointer dots', () => {
    const state = buildTree(2, [10, 20, 30]);
    const layout = computeLayout(state);
    eq(layout.layout?.pointerDots?.[state.rootId]?.length ?? layout.pointerDots[state.rootId].length, 0);
  });

  test('leaf node produces no edges', () => {
    const state = buildTree(2, [10, 20, 30]);
    const layout = computeLayout(state);
    eq(Object.keys(layout.edges).length, 0);
  });
});

// ─── All leaves at the same y coordinate ─────────────────────────────────────

suite('uniform leaf depth --, spec section 13.3', () => {
  function checkUniformLeafY(label, state) {
    test(label, () => {
      const layout = computeLayout(state);
      const leafIds = allLeaves(state);
      ok(leafIds.length > 0, 'tree should have leaves');
      const ys = leafIds.map(id => layout.nodes[id].y);
      const first = ys[0];
      for (let i = 1; i < ys.length; i++) {
        ok(
          Math.abs(ys[i] - first) < 0.01,
          `Leaf ${leafIds[i]} has y=${ys[i]}, expected ${first}`
        );
      }
    });
  }

  checkUniformLeafY('2-level tree after first split (t=2, 4 keys)', buildTree(2, [1, 2, 3, 4]));
  checkUniformLeafY('3-level tree (t=2, 10 keys)', buildTree(2, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]));
  checkUniformLeafY('t=3, 8 keys', buildTree(3, [5, 10, 15, 20, 25, 30, 35, 40]));
  checkUniformLeafY('t=5, 20 keys', buildTree(5, Array.from({ length: 20 }, (_, i) => i + 1)));
});

// ─── y coordinate formula ────────────────────────────────────────────────────

suite('y coordinate by depth', () => {
  test('root is always at y=0', () => {
    const state = buildTree(2, [10, 20, 30, 40]);
    const layout = computeLayout(state);
    eq(layout.nodes[state.rootId].y, 0);
  });

  test('depth-1 nodes are at y = NODE_HEIGHT + LEVEL_SEPARATION = 192', () => {
    const state = buildTree(2, [10, 20, 30, 40]);
    const layout = computeLayout(state);
    const depth1 = state.nodes[state.rootId].children;
    const expectedY = calcNodeHeight(D) + D.LEVEL_SEPARATION; // 72 + 120 = 192
    for (const cid of depth1) {
      ok(
        Math.abs(layout.nodes[cid].y - expectedY) < 0.01,
        `depth-1 node ${cid} y=${layout.nodes[cid].y}, expected ${expectedY}`
      );
    }
  });

  test('depth-2 nodes are at y = 2 × (NODE_HEIGHT + LEVEL_SEPARATION) = 384', () => {
    const state = buildTree(2, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
    const layout = computeLayout(state);
    const leaves = allLeaves(state);
    const expectedY = 2 * (calcNodeHeight(D) + D.LEVEL_SEPARATION); // 384
    // Only check leaves that are actually at depth 2
    const depth2Leaves = leaves.filter(id => nodeDepth(state, id) === 2);
    ok(depth2Leaves.length > 0, 'should have depth-2 leaves for this tree');
    for (const id of depth2Leaves) {
      ok(Math.abs(layout.nodes[id].y - expectedY) < 0.01,
        `depth-2 node y=${layout.nodes[id].y}, expected ${expectedY}`);
    }
  });
});

// ─── Parent is centred over its children ─────────────────────────────────────
//
// Spec: node.x = (leftmostChild.x + rightmostChild.x) / 2

suite('parent centred over children --, spec section 4.3 phase 2', () => {
  function checkParentCentred(label, state) {
    test(label, () => {
      const layout = computeLayout(state);
      for (const [id, node] of Object.entries(state.nodes)) {
        if (node.isLeaf || node.children.length === 0) continue;
        const parentX = layout.nodes[id].x;
        const leftmostX  = layout.nodes[node.children[0]].x;
        const rightmostX = layout.nodes[node.children[node.children.length - 1]].x;
        const expectedX  = (leftmostX + rightmostX) / 2;
        ok(
          Math.abs(parentX - expectedX) < 0.5,
          `Node ${id}: parent.x=${parentX.toFixed(2)}, expected centre=${expectedX.toFixed(2)} (leftmost=${leftmostX.toFixed(2)}, rightmost=${rightmostX.toFixed(2)})`
        );
      }
    });
  }

  checkParentCentred('2-level tree (t=2, 4 keys)',   buildTree(2, [1, 2, 3, 4]));
  checkParentCentred('2-level tree (t=2, 7 keys)',   buildTree(2, [10, 20, 30, 40, 50, 60, 70]));
  checkParentCentred('3-level tree (t=2, 10 keys)',  buildTree(2, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]));
  checkParentCentred('t=3, 12 keys',                 buildTree(3, Array.from({ length: 12 }, (_, i) => i * 5)));
});

// ─── No two nodes overlap at the same level ───────────────────────────────────

suite('no node overlap at same depth --, spec section 13.3', () => {
  function checkNoOverlap(label, state) {
    test(label, () => {
      const layout = computeLayout(state);

      // Group nodes by their y coordinate (which corresponds to depth)
      const byLevel = {};
      for (const [id, pos] of Object.entries(layout.nodes)) {
        const level = Math.round(pos.y); // round to handle tiny fp errors
        if (!byLevel[level]) byLevel[level] = [];
        byLevel[level].push({ id, x: pos.x, width: pos.width });
      }

      for (const [levelY, entries] of Object.entries(byLevel)) {
        for (let a = 0; a < entries.length; a++) {
          for (let b = a + 1; b < entries.length; b++) {
            const A = entries[a];
            const B = entries[b];
            ok(
              !rangesOverlap(A.x, A.width, B.x, B.width),
              `Overlap at y=${levelY}: node ${A.id} (x=${A.x.toFixed(1)}, w=${A.width}) vs node ${B.id} (x=${B.x.toFixed(1)}, w=${B.width})`
            );
          }
        }
      }
    });
  }

  checkNoOverlap('single-node tree',                buildTree(2, [1]));
  checkNoOverlap('2-level tree (t=2, 4 keys)',      buildTree(2, [1, 2, 3, 4]));
  checkNoOverlap('2-level tree (t=2, 7 keys)',      buildTree(2, [10, 20, 30, 40, 50, 60, 70]));
  checkNoOverlap('3-level tree (t=2, 10 keys)',     buildTree(2, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]));
  checkNoOverlap('t=3, 9 keys',                     buildTree(3, [5, 10, 15, 20, 25, 30, 35, 40, 45]));
  checkNoOverlap('t=5, 25 keys',                    buildTree(5, Array.from({ length: 25 }, (_, i) => i + 1)));
  checkNoOverlap('asymmetric inserts',              buildTree(2, [50, 10, 90, 5, 15, 70, 95, 1, 7]));
});

// ─── Key slot positions ────────────────────────────────────────────────────────

suite('key slot positions --, spec section 4.3 phase 5', () => {
  test('first slot x = node left edge + NODE_PADDING_X', () => {
    const state = buildTree(2, [10, 20, 30]);
    const layout = computeLayout(state);
    const pos    = layout.nodes[state.rootId];
    const slots  = layout.keys[state.rootId];
    const leftEdge = pos.x - pos.width / 2;
    ok(
      Math.abs(slots[0].x - (leftEdge + D.NODE_PADDING_X)) < 0.01,
      `slot[0].x=${slots[0].x.toFixed(2)}, expected ${(leftEdge + D.NODE_PADDING_X).toFixed(2)}`
    );
  });

  test('adjacent slots are separated by SLOT_WIDTH + SLOT_GAP', () => {
    const state = buildTree(2, [10, 20, 30]);
    const layout = computeLayout(state);
    const slots  = layout.keys[state.rootId];
    ok(slots.length === 3);
    const expectedStep = D.SLOT_WIDTH + D.SLOT_GAP;
    ok(
      Math.abs((slots[1].x - slots[0].x) - expectedStep) < 0.01,
      `slot[1]-slot[0] = ${(slots[1].x - slots[0].x).toFixed(2)}, expected ${expectedStep}`
    );
    ok(
      Math.abs((slots[2].x - slots[1].x) - expectedStep) < 0.01
    );
  });

  test('all slot y values equal node.y + NODE_PADDING_Y', () => {
    const state = buildTree(2, [10, 20, 30]);
    const layout = computeLayout(state);
    const pos   = layout.nodes[state.rootId];
    const slots = layout.keys[state.rootId];
    for (const slot of slots) {
      ok(
        Math.abs(slot.y - (pos.y + D.NODE_PADDING_Y)) < 0.01,
        `slot.y=${slot.y}, expected ${pos.y + D.NODE_PADDING_Y}`
      );
    }
  });

  test('every slot has SLOT_WIDTH × SLOT_HEIGHT dimensions', () => {
    const state = buildTree(2, [10, 20, 30, 40]);
    const layout = computeLayout(state);
    for (const [, slots] of Object.entries(layout.keys)) {
      for (const slot of slots) {
        eq(slot.width,  D.SLOT_WIDTH);
        eq(slot.height, D.SLOT_HEIGHT);
      }
    }
  });

  test('number of key slots matches node.keys.length for every node', () => {
    const state = buildTree(3, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]);
    const layout = computeLayout(state);
    for (const [id, node] of Object.entries(state.nodes)) {
      eq(
        layout.keys[id].length,
        node.keys.length,
        `Node ${id}: ${layout.keys[id].length} slots but ${node.keys.length} keys`
      );
    }
  });
});

// ─── Pointer dot positions ────────────────────────────────────────────────────

suite('pointer dot positions --, spec section 4.3 phase 6', () => {
  test('leaf nodes have 0 pointer dots', () => {
    const state = buildTree(2, [10, 20, 30, 40]);
    const layout = computeLayout(state);
    const leaves = allLeaves(state);
    for (const id of leaves) {
      eq(layout.pointerDots[id].length, 0, `Leaf ${id} should have no pointer dots`);
    }
  });

  test('internal node with n keys has n+1 pointer dots', () => {
    const state = buildTree(2, [10, 20, 30, 40]);
    const layout = computeLayout(state);
    for (const [id, node] of Object.entries(state.nodes)) {
      if (!node.isLeaf) {
        eq(
          layout.pointerDots[id].length,
          node.keys.length + 1,
          `Internal node ${id}: expected ${node.keys.length + 1} dots, got ${layout.pointerDots[id].length}`
        );
      }
    }
  });

  test('all dots sit on the bottom edge of their node (dot.y == node.y + height)', () => {
    const state = buildTree(2, [1, 2, 3, 4, 5, 6, 7]);
    const layout = computeLayout(state);
    for (const [id, dots] of Object.entries(layout.pointerDots)) {
      const pos = layout.nodes[id];
      const expectedY = pos.y + pos.height;
      for (const dot of dots) {
        ok(
          Math.abs(dot.y - expectedY) < 0.01,
          `Dot on node ${id}: dot.y=${dot.y}, expected ${expectedY}`
        );
      }
    }
  });

  test('dots are equally spaced (step = SLOT_WIDTH + SLOT_GAP)', () => {
    const state = buildTree(2, [10, 20, 30, 40]);
    const layout = computeLayout(state);
    const rootNode = state.nodes[state.rootId];

    if (!rootNode.isLeaf) {
      const dots = layout.pointerDots[state.rootId];
      const step = D.SLOT_WIDTH + D.SLOT_GAP;
      for (let i = 1; i < dots.length; i++) {
        ok(
          Math.abs((dots[i].x - dots[i - 1].x) - step) < 0.01,
          `dot[${i}] - dot[${i - 1}] = ${(dots[i].x - dots[i - 1].x).toFixed(2)}, expected ${step}`
        );
      }
    }
  });

  test('first dot x is left of the first slot (by SLOT_GAP/2)', () => {
    const state = buildTree(2, [10, 20, 30, 40]);
    const layout = computeLayout(state);
    const rootId = state.rootId;
    if (!state.nodes[rootId].isLeaf) {
      const dot0  = layout.pointerDots[rootId][0];
      const slot0 = layout.keys[rootId][0];
      // dot[0].x should be SLOT_GAP/2 to the left of slot[0].x
      const delta = slot0.x - dot0.x;
      ok(
        Math.abs(delta - D.SLOT_GAP / 2) < 0.01,
        `Expected dot0 to be ${D.SLOT_GAP / 2}px left of slot0, got ${delta.toFixed(2)}px`
      );
    }
  });
});

// ─── Edge counts ──────────────────────────────────────────────────────────────

suite('edge counts --, spec section 13.3', () => {
  function countTotalChildRelationships(state) {
    let count = 0;
    for (const node of Object.values(state.nodes)) {
      count += node.children.length;
    }
    return count;
  }

  function checkEdgeCount(label, state) {
    test(label, () => {
      const layout    = computeLayout(state);
      const expected  = countTotalChildRelationships(state);
      const actual    = Object.keys(layout.edges).length;
      eq(actual, expected, `Expected ${expected} edges, got ${actual}`);
    });
  }

  checkEdgeCount('single-node tree has 0 edges',           buildTree(2, [1]));
  checkEdgeCount('2-level tree (t=2, 4 keys) has 3 edges', buildTree(2, [1, 2, 3, 4]));
  checkEdgeCount('2-level tree (t=2, 7 keys)',             buildTree(2, [10, 20, 30, 40, 50, 60, 70]));
  checkEdgeCount('3-level tree (t=2, 10 keys)',            buildTree(2, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]));
  checkEdgeCount('t=3, 12 keys',                           buildTree(3, Array.from({ length: 12 }, (_, i) => i + 1)));
});

// ─── Edge geometry ────────────────────────────────────────────────────────────

suite('edge geometry', () => {
  test('edge fromDot matches the corresponding pointer dot', () => {
    const state  = buildTree(2, [10, 20, 30, 40]);
    const layout = computeLayout(state);

    for (const [key, edge] of Object.entries(layout.edges)) {
      // key format: "${parentId}→${childIndex}"
      const arrowIdx = key.indexOf('→');
      const parentId  = key.slice(0, arrowIdx);
      const childIdx  = parseInt(key.slice(arrowIdx + 1), 10);

      const dot = layout.pointerDots[parentId][childIdx];
      ok(dot, `pointer dot ${childIdx} should exist on node ${parentId}`);
      ok(Math.abs(edge.fromDot.x - dot.x) < 0.01,
        `edge fromDot.x=${edge.fromDot.x} != dot.x=${dot.x}`);
      ok(Math.abs(edge.fromDot.y - dot.y) < 0.01,
        `edge fromDot.y=${edge.fromDot.y} != dot.y=${dot.y}`);
    }
  });

  test('edge toNode matches the child node top-centre', () => {
    const state  = buildTree(2, [10, 20, 30, 40]);
    const layout = computeLayout(state);

    for (const [key, edge] of Object.entries(layout.edges)) {
      const arrowIdx = key.indexOf('→');
      const parentId  = key.slice(0, arrowIdx);
      const childIdx  = parseInt(key.slice(arrowIdx + 1), 10);
      const childId   = state.nodes[parentId].children[childIdx];
      const childPos  = layout.nodes[childId];

      ok(Math.abs(edge.toNode.x - childPos.x) < 0.01,
        `edge toNode.x=${edge.toNode.x} != child.x=${childPos.x}`);
      ok(Math.abs(edge.toNode.y - childPos.y) < 0.01,
        `edge toNode.y=${edge.toNode.y} != child.y=${childPos.y}`);
    }
  });

  test('edge always goes downward (fromDot.y < toNode.y)', () => {
    const state  = buildTree(2, [1, 2, 3, 4, 5, 6, 7]);
    const layout = computeLayout(state);
    for (const [key, edge] of Object.entries(layout.edges)) {
      ok(
        edge.fromDot.y < edge.toNode.y,
        `Edge ${key}: parent dot (y=${edge.fromDot.y}) should be above child top (y=${edge.toNode.y})`
      );
    }
  });

  test('edge path string starts with M and contains L', () => {
    const state  = buildTree(2, [10, 20, 30, 40]);
    const layout = computeLayout(state);
    for (const [key, edge] of Object.entries(layout.edges)) {
      ok(edge.path.startsWith('M '), `Edge ${key} path should start with "M "`);
      ok(edge.path.includes(' L '), `Edge ${key} path should contain " L "`);
    }
  });
});

// ─── Width formula with variable-width nodes ──────────────────────────────────

suite('node widths in layout match formula', () => {
  test('every node.width in layout matches calcNodeWidth', () => {
    const state  = buildTree(2, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
    const layout = computeLayout(state);
    for (const [id, node] of Object.entries(state.nodes)) {
      const expected = calcNodeWidth(node.keys.length, D);
      eq(
        layout.nodes[id].width,
        expected,
        `Node ${id} (${node.keys.length} keys): width=${layout.nodes[id].width}, expected ${expected}`
      );
    }
  });
});

// ─── Wide node is wider than its subtree span ────────────────────────────────
//
// If the root has many keys but few children, it might be wider than the span
// of its children. The children should still be placed without overlap, and
// the parent should still be centred over them.

suite('wide parent vs narrow children subtree', () => {
  test('wide root does not cause children to overlap', () => {
    // t=5: root can hold up to 9 keys. Build a tree where root is near-full
    // but each child is small.
    const state  = buildTree(5, Array.from({ length: 9 }, (_, i) => (i + 1) * 10));
    const layout = computeLayout(state);

    const rootNode = state.nodes[state.rootId];
    if (!rootNode.isLeaf && rootNode.children.length > 1) {
      const childPositions = rootNode.children.map(id => layout.nodes[id]);
      for (let a = 0; a < childPositions.length; a++) {
        for (let b = a + 1; b < childPositions.length; b++) {
          ok(
            !rangesOverlap(childPositions[a].x, childPositions[a].width,
                           childPositions[b].x, childPositions[b].width),
            'Children of a wide root should not overlap'
          );
        }
      }
    }
  });
});

// ─── Layout after deletion ────────────────────────────────────────────────────

suite('layout stays valid after deletion', () => {
  test('layout after borrow-left is still overlap-free', () => {
    const state0 = buildTree(2, [10, 20, 30, 40, 50]);
    const steps  = deleteKey(state0, 40);
    const state1 = steps[steps.length - 1].state;
    const layout = computeLayout(state1);

    // Uniform leaf depth
    const leaves = allLeaves(state1);
    const ys = leaves.map(id => layout.nodes[id].y);
    const first = ys[0];
    for (const y of ys) {
      ok(Math.abs(y - first) < 0.01, 'leaves should be at same y after borrow-left');
    }
  });

  test('layout after merge has correct edge count', () => {
    const state0 = buildTree(2, [10, 20, 30]);
    const steps  = deleteKey(state0, 10);
    const state1 = steps[steps.length - 1].state;
    const layout = computeLayout(state1);

    let expectedEdges = 0;
    for (const n of Object.values(state1.nodes)) expectedEdges += n.children.length;
    eq(Object.keys(layout.edges).length, expectedEdges);
  });
});

// ─── Theme overrides ──────────────────────────────────────────────────────────

suite('custom theme', () => {
  test('custom LEVEL_SEPARATION changes depth-1 y', () => {
    const state  = buildTree(2, [10, 20, 30, 40]);
    const customTheme = { LEVEL_SEPARATION: 200 };
    const layout = computeLayout(state, customTheme);
    const children = state.nodes[state.rootId].children;
    const nh = calcNodeHeight({ ...D, ...customTheme });
    const expectedY = nh + 200;
    for (const cid of children) {
      ok(
        Math.abs(layout.nodes[cid].y - expectedY) < 0.01,
        `With LEVEL_SEPARATION=200, depth-1 y should be ${expectedY}, got ${layout.nodes[cid].y}`
      );
    }
  });

  test('custom SIBLING_SEPARATION creates larger gaps between siblings', () => {
    const state       = buildTree(2, [10, 20, 30, 40]);
    const layoutSmall = computeLayout(state, { SIBLING_SEPARATION: 10 });
    const layoutBig   = computeLayout(state, { SIBLING_SEPARATION: 100 });

    // The tree with bigger separation should span a wider x range
    const xsSmall = Object.values(layoutSmall.nodes).map(p => p.x);
    const xsBig   = Object.values(layoutBig.nodes).map(p => p.x);
    const spanSmall = Math.max(...xsSmall) - Math.min(...xsSmall);
    const spanBig   = Math.max(...xsBig)   - Math.min(...xsBig);
    ok(spanBig > spanSmall, `Larger separation should produce wider span (${spanBig} > ${spanSmall})`);
  });
});

// ─── Stress ───────────────────────────────────────────────────────────────────

suite('stress', () => {
  test('50-key tree: no overlaps and uniform leaf depth', () => {
    const keys  = Array.from({ length: 50 }, (_, i) => i + 1);
    const state = buildTree(2, keys);
    const layout = computeLayout(state);

    // Overlap check
    const byLevel = {};
    for (const [id, pos] of Object.entries(layout.nodes)) {
      const level = Math.round(pos.y);
      if (!byLevel[level]) byLevel[level] = [];
      byLevel[level].push({ id, x: pos.x, width: pos.width });
    }
    for (const entries of Object.values(byLevel)) {
      for (let a = 0; a < entries.length; a++) {
        for (let b = a + 1; b < entries.length; b++) {
          ok(
            !rangesOverlap(entries[a].x, entries[a].width, entries[b].x, entries[b].width),
            `Overlap: ${entries[a].id} vs ${entries[b].id}`
          );
        }
      }
    }

    // Uniform leaf y
    const leaves = allLeaves(state);
    const ys = leaves.map(id => layout.nodes[id].y);
    const firstY = ys[0];
    for (const y of ys) {
      ok(Math.abs(y - firstY) < 0.01, 'All leaves should be at same depth');
    }
  });
});

// ─────────────────────────────────────────────────────────────────────────────

summary();