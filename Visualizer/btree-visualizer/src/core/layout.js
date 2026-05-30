// Layout engine for the B-tree visualizer.
//
// Pure function --, no DOM access, no D3, no imports from other project modules.
// You can unit-test this completely in isolation with just a plain state object.
//
// The main export is:
//   computeLayout(state, theme?) → LayoutMap
//
// LayoutMap shape is specified in architecture section 4.1.
// All coordinates are in pixels, absolute (not relative to any container).
//   node.x  = horizontal centre of the node card
//   node.y  = top edge of the node card

// ─── Default theme constants ─────────────────────────────────────────────────
// These map 1-to-1 to spec section 2.3. Override any of them by passing a
// theme object as the second argument to computeLayout().

const DEFAULTS = {
  SLOT_WIDTH:         52,
  SLOT_HEIGHT:        56,
  SLOT_GAP:            4,   // gap between adjacent key slots inside a node
  NODE_PADDING_X:     10,   // horizontal padding inside the node card
  NODE_PADDING_Y:      8,   // vertical padding top and bottom
  LEVEL_SEPARATION:  120,   // vertical gap between tree levels
  SIBLING_SEPARATION: 24,   // horizontal gap between sibling subtrees
};

// ─── Width / height formulas (spec section 4.2) ───────────────────────────────

// Returns the pixel width of a node card given the number of keys it holds.
// We guard against 0-key nodes (temporarily empty root during deletion) by
// keeping the gap count non-negative so the formula never goes negative.
// Minimum width = 1-key width so 0-key shell nodes (new root in SPLIT_ROOT)
// are still wide enough to be visible.
function calcNodeWidth(keyCount, C) {
  const k = Math.max(keyCount, 1);  // treat 0-key shell as 1-key for width
  return k * C.SLOT_WIDTH + Math.max(k - 1, 0) * C.SLOT_GAP + 2 * C.NODE_PADDING_X;
}

// Height never changes --, always padding + one row of slots + padding.
function calcNodeHeight(C) {
  return C.NODE_PADDING_Y * 2 + C.SLOT_HEIGHT;
}

// ─── Phase 1: collect leaves in in-order traversal order ─────────────────────
//
// B-trees are binary-search-compatible: an in-order walk visits keys in sorted
// order. The leaves in that same order are the ones we space horizontally.

function collectLeavesInOrder(nodeId, nodes, result) {
  const node = nodes[nodeId];
  if (node.isLeaf) {
    result.push(nodeId);
    return;
  }
  for (const childId of node.children) {
    collectLeavesInOrder(childId, nodes, result);
  }
}

// ─── Depth map ────────────────────────────────────────────────────────────────

function buildDepthMap(nodeId, nodes, map, depth) {
  map[nodeId] = depth;
  const node = nodes[nodeId];
  if (!node.isLeaf && node.children) {
    for (const childId of node.children) {
      buildDepthMap(childId, nodes, map, depth + 1);
    }
  }
}

// ─── Phase 2: bottom-up x for internal nodes ─────────────────────────────────
//
// Spec formula: node.x = (leftmostChild.x + rightmostChild.x) / 2
//
// We process internal nodes from deepest level to shallowest so that every
// node's children already have x positions when we get to it.
//
// Note on the "wide parent" case from spec section 4.3:
// For any valid B-tree with t≥2, an internal node with k keys has k+1 children.
// The children's visual span is always wider than the node itself:
//   node width  = 56k + 16
//   children span ≥ (k+1)×min_leaf_width + k×SIBLING_SEPARATION ≥ 96k + 72
// Since 56k+16 < 96k+72 for all k≥0, the "children narrower than parent"
// situation never occurs for structurally valid trees. We skip that branch.

function assignInternalXPositions(rootId, nodes, positions, depthMap) {
  // Gather all internal node IDs, sort deepest-first so children are
  // processed before their parents.
  const internals = Object.keys(nodes).filter(id => !nodes[id].isLeaf);
  internals.sort((a, b) => depthMap[b] - depthMap[a]);

  for (const nodeId of internals) {
    const node = nodes[nodeId];
    const leftChildId  = node.children[0];
    const rightChildId = node.children[node.children.length - 1];
    positions[nodeId].x = (positions[leftChildId].x + positions[rightChildId].x) / 2;
  }
}

// ─── Phase 4: centre the tree at x = 0 ───────────────────────────────────────
//
// After the two phases above, the root sits somewhere to the right of x=0
// because leaf[0].x was placed at 0. We subtract the root's x from every
// node so the root ends up at x=0. The SVG viewport then applies its own
// transform to put (0, 0) in the visual centre of the canvas.

function centreTree(positions, rootId) {
  const offset = positions[rootId].x;
  for (const id of Object.keys(positions)) {
    positions[id].x -= offset;
  }
}

// ─── Phase 5: key slot positions ─────────────────────────────────────────────
//
// Slot coordinates are absolute. Spec formula (section 4.3):
//   slot[i].x = NODE_PADDING_X + i × (SLOT_WIDTH + SLOT_GAP)   (relative to left edge)
// We convert to absolute by adding the node's left edge (cx − width/2).

function computeKeySlots(nodeId, positions, nodes, C) {
  const pos      = positions[nodeId];
  const node     = nodes[nodeId];
  const leftEdge = pos.x - pos.width / 2;

  return node.keys.map((_, i) => ({
    x:      leftEdge + C.NODE_PADDING_X + i * (C.SLOT_WIDTH + C.SLOT_GAP),
    y:      pos.y + C.NODE_PADDING_Y,
    width:  C.SLOT_WIDTH,
    height: C.SLOT_HEIGHT,
  }));
}

// ─── Phase 6: child pointer dot positions ────────────────────────────────────
//
// Only internal nodes get dots --, leaves have nothing to point to.
// There are (keys.length + 1) dots: one to the left of the first slot,
// then one to the right of every slot.
//
// Spec formula (relative to node left edge):
//   dot[i].x = NODE_PADDING_X + i × (SLOT_WIDTH + SLOT_GAP) − SLOT_GAP/2
//   dot[i].y = node.height   (bottom edge of the card)

function computePointerDots(nodeId, positions, nodes, C) {
  const pos  = positions[nodeId];
  const node = nodes[nodeId];

  if (node.isLeaf) return [];

  const leftEdge = pos.x - pos.width / 2;
  const bottomY  = pos.y + pos.height;
  const dotCount = node.keys.length + 1;

  return Array.from({ length: dotCount }, (_, i) => ({
    x: leftEdge + C.NODE_PADDING_X + i * (C.SLOT_WIDTH + C.SLOT_GAP) - C.SLOT_GAP / 2,
    y: bottomY,
  }));
}

// ─── Edge computation ─────────────────────────────────────────────────────────
//
// One edge per (parent, childIndex) pair. Key format per spec section 4.1:
//   `${parentId}→${childIndex}`
//
// fromDot  = the pointer dot on the parent's bottom edge
// toNode   = the top-centre of the child node card
// path     = SVG path string --, straight line; the animation layer can
//            override or morph this during transitions.

function computeEdges(nodeId, positions, nodes, pointerDots) {
  const node   = nodes[nodeId];
  const result = {};

  if (node.isLeaf || !node.children) return result;

  const dots = pointerDots[nodeId] || [];

  for (let i = 0; i < node.children.length; i++) {
    const childId  = node.children[i];
    const childPos = positions[childId];

    if (!childPos) continue; // shouldn't happen in a valid tree

    const from = dots[i] || { x: positions[nodeId].x, y: positions[nodeId].y + positions[nodeId].height };
    const to   = { x: childPos.x, y: childPos.y };

    result[`${nodeId}→${i}`] = {
      fromDot: { x: from.x, y: from.y },
      toNode:  { x: to.x,   y: to.y   },
      path:    `M ${from.x} ${from.y} L ${to.x} ${to.y}`,
    };
  }

  return result;
}

// ─── Main export ──────────────────────────────────────────────────────────────

/**
 * computeLayout(state, theme?)  →  LayoutMap
 *
 * Implements the six-phase algorithm from spec section 4.3.
 *
 * @param {BTreeState} state  - Plain state object (from BTree.js / insert / delete)
 * @param {object}     theme  - Optional overrides for visual constants
 * @returns {LayoutMap}
 */
function computeLayout(state, theme = {}) {
  const C = { ...DEFAULTS, ...theme };
  const { nodes, rootId } = state;

  if (!nodes || !rootId || !nodes[rootId]) {
    return { nodes: {}, keys: {}, pointerDots: {}, edges: {} };
  }

  // ── Only layout nodes reachable from the root ─────────────────────────────
  // During intermediate animation steps (e.g. SPLIT_EXECUTE) a new node may
  // exist in `nodes` but not yet be wired into parent.children. If we include
  // it in the layout its depthMap entry is undefined → NaN coordinates.
  const reachable = new Set();
  const queue = [rootId];
  while (queue.length > 0) {
    const id = queue.shift();
    if (reachable.has(id)) continue;
    reachable.add(id);
    const n = nodes[id];
    if (n && !n.isLeaf && n.children) {
      for (const cid of n.children) {
        if (nodes[cid]) queue.push(cid);
      }
    }
  }
  // Use reachable nodes only for the layout pass
  const layoutNodes = {};
  for (const id of reachable) layoutNodes[id] = nodes[id];

  const NH = calcNodeHeight(C);

  // Build a depth map so y coordinates are correct without multiple traversals
  const depthMap = {};
  buildDepthMap(rootId, layoutNodes, depthMap, 0);

  // Initialise positions with correct heights --, x gets filled in below
  const positions = {};
  for (const nodeId of Object.keys(layoutNodes)) {
    positions[nodeId] = {
      x:      0,
      y:      depthMap[nodeId] * (NH + C.LEVEL_SEPARATION),
      width:  calcNodeWidth(layoutNodes[nodeId].keys.length, C),
      height: NH,
    };
  }

  // Phase 1: assign x to leaves in in-order traversal order.
  const leavesInOrder = [];
  collectLeavesInOrder(rootId, layoutNodes, leavesInOrder);

  if (leavesInOrder.length > 0) {
    positions[leavesInOrder[0]].x = 0;

    for (let i = 1; i < leavesInOrder.length; i++) {
      const prevId = leavesInOrder[i - 1];
      const curId  = leavesInOrder[i];
      positions[curId].x =
        positions[prevId].x
        + positions[prevId].width / 2
        + C.SIBLING_SEPARATION
        + positions[curId].width / 2;
    }
  }

  // Phase 2: bottom-up x for internal nodes.
  assignInternalXPositions(rootId, layoutNodes, positions, depthMap);

  // Phase 4: translate so root sits at x = 0.
  centreTree(positions, rootId);

  // Phases 5 & 6: slots and pointer dots
  const layoutKeys  = {};
  const layoutDots  = {};
  const layoutEdges = {};

  for (const nodeId of Object.keys(layoutNodes)) {
    layoutKeys[nodeId] = computeKeySlots(nodeId, positions, layoutNodes, C);
    layoutDots[nodeId] = computePointerDots(nodeId, positions, layoutNodes, C);
  }

  // Edges need dots already computed
  for (const nodeId of Object.keys(layoutNodes)) {
    Object.assign(layoutEdges, computeEdges(nodeId, positions, layoutNodes, layoutDots));
  }

  return {
    nodes:       positions,
    keys:        layoutKeys,
    pointerDots: layoutDots,
    edges:       layoutEdges,
  };
}

// Export constants so tests can reference the exact values the engine uses
computeLayout.DEFAULTS = DEFAULTS;

module.exports = { computeLayout, calcNodeWidth, calcNodeHeight };