// Core B-tree state management. All functions here are pure --, no side effects,
// no mutation of the input state, no step generation.
//
// The BTreeState schema is defined in spec section 3.1.

const { generateId } = require('./shared');

// Creates an empty B-tree with minimum degree t.
// t must be >= 2 (t=2 is a 2-3-4 tree, the minimum valid B-tree).
function createTree(t = 2) {
  if (t < 2) throw new Error(`t must be >= 2, got ${t}`);

  const rootId = generateId('root');
  return {
    t,
    rootId,
    nodes: {
      [rootId]: {
        id: rootId,
        keys: [],
        children: [],
        isLeaf: true,
        parentId: null,
      },
    },
  };
}

// --- Derived property helpers ---
// These are called frequently by the algorithm modules. Keep them fast.

function isFull(node, t) {
  return node.keys.length === 2 * t - 1;
}

function isOverflow(node, t) {
  // A node is in overflow if it temporarily holds 2t keys (one too many).
  // This happens for exactly one step during insert, before the split fires.
  return node.keys.length > 2 * t - 1;
}

function isUnderflow(node, state) {
  // Root is exempt --, it can legally have just 1 key.
  if (node.id === state.rootId) return false;
  return node.keys.length < state.t - 1;
}

// Returns all keys in sorted order via in-order traversal.
function inOrderKeys(state) {
  const result = [];

  function traverse(nodeId) {
    const n = state.nodes[nodeId];
    if (!n) return;
    for (let i = 0; i < n.keys.length; i++) {
      if (!n.isLeaf) traverse(n.children[i]);
      result.push(n.keys[i]);
    }
    if (!n.isLeaf) traverse(n.children[n.keys.length]);
  }

  traverse(state.rootId);
  return result;
}

// Returns the height of the tree (number of levels, root = level 1).
function height(state) {
  let h = 0;
  let nodeId = state.rootId;
  while (nodeId) {
    h++;
    const n = state.nodes[nodeId];
    nodeId = n.isLeaf ? null : n.children[0];
  }
  return h;
}

// Validates all B-tree invariants. Returns an array of error strings.
// An empty array means the tree is valid.
//
// Used heavily in tests but also useful during development --, call this after
// each operation to catch bugs early.
function validate(state) {
  const errors = [];
  const { t, rootId, nodes } = state;

  if (!nodes[rootId]) {
    errors.push(`Root node '${rootId}' not in nodes map`);
    return errors; // nothing else we can check
  }

  // Collect leaf depths for the uniform-depth check later
  const leafDepths = [];

  for (const [id, node] of Object.entries(nodes)) {
    // --- Key count ---
    if (id !== rootId) {
      if (node.keys.length < t - 1) {
        errors.push(
          `Node ${id}: has ${node.keys.length} keys, minimum is t-1=${t - 1}`
        );
      }
    } else {
      // Non-trivial root must have at least 1 key
      if (Object.keys(nodes).length > 1 && node.keys.length < 1) {
        errors.push(`Root ${id}: must have at least 1 key when tree is non-empty`);
      }
    }

    if (node.keys.length > 2 * t - 1) {
      errors.push(
        `Node ${id}: has ${node.keys.length} keys, maximum is 2t-1=${2 * t - 1}`
      );
    }

    // --- Keys are sorted (strict ascending) ---
    for (let i = 0; i < node.keys.length - 1; i++) {
      if (node.keys[i] >= node.keys[i + 1]) {
        errors.push(
          `Node ${id}: keys not strictly sorted at index ${i} (${node.keys[i]} >= ${node.keys[i + 1]})`
        );
      }
    }

    // --- Leaf/internal consistency ---
    if (node.isLeaf) {
      if (node.children.length !== 0) {
        errors.push(`Node ${id}: marked isLeaf but has ${node.children.length} children`);
      }
    } else {
      const expected = node.keys.length + 1;
      if (node.children.length !== expected) {
        errors.push(
          `Node ${id}: internal node has ${node.children.length} children, expected ${expected}`
        );
      }
    }

    // --- parentId consistency ---
    if (id === rootId) {
      if (node.parentId !== null) {
        errors.push(`Root ${id}: parentId should be null, got '${node.parentId}'`);
      }
    } else {
      if (!node.parentId) {
        errors.push(`Node ${id}: non-root has no parentId`);
      } else if (!nodes[node.parentId]) {
        errors.push(`Node ${id}: parentId '${node.parentId}' not in nodes map`);
      }
    }

    // --- Children exist and point back correctly ---
    for (const childId of node.children) {
      if (!nodes[childId]) {
        errors.push(`Node ${id}: child '${childId}' not in nodes map`);
        continue;
      }
      if (nodes[childId].parentId !== id) {
        errors.push(
          `Node ${id}: child ${childId}.parentId is '${nodes[childId].parentId}', expected '${id}'`
        );
      }
    }

    // Collect leaf depths while we're iterating
    if (node.isLeaf) {
      // compute depth by walking up via parentId
      let d = 0;
      let cur = node;
      while (cur.parentId) {
        d++;
        cur = nodes[cur.parentId];
        if (!cur) break; // broken parent chain --, already caught above
      }
      leafDepths.push(d);
    }
  }

  // --- All leaves at same depth ---
  if (leafDepths.length > 1) {
    const first = leafDepths[0];
    const bad = leafDepths.filter(d => d !== first);
    if (bad.length > 0) {
      errors.push(
        `Leaves are not at uniform depth. Expected all at depth ${first}, found: ${[...new Set(leafDepths)].sort().join(', ')}`
      );
    }
  }

  // --- In-order traversal is strictly sorted ---
  const keys = inOrderKeys(state);
  for (let i = 0; i < keys.length - 1; i++) {
    if (keys[i] >= keys[i + 1]) {
      errors.push(
        `In-order traversal not sorted at index ${i}: ${keys[i]} >= ${keys[i + 1]}`
      );
    }
  }

  return errors;
}

module.exports = { createTree, validate, isFull, isOverflow, isUnderflow, inOrderKeys, height };