// Insert operation. Uses proactive splitting (split on the way down) so we
// never need a second upward pass. Returns Step[] --, the input state is never
// mutated; we work on a deep clone throughout.
//
// Pseudocode line indices match spec section 5.2.

const { ACTIONS, NODE_ROLES, KEY_ROLES, EDGE_ROLES } = require('./constants');
const { generateId, cloneState, createStep } = require('./shared');
const { isFull } = require('./btree');

const PSEUDOCODE = [
  'function insert(key):',                                         // 0
  '  if root is full (2t-1 keys):',                               // 1
  '    newRoot = createNode()',                                    // 2
  '    newRoot.children = [root]',                                 // 3
  '    splitChild(newRoot, 0, root)',                              // 4
  '    root = newRoot',                                            // 5
  '  insertNonFull(root, key)',                                    // 6
  '',                                                              // 7
  'function insertNonFull(node, key):',                           // 8
  '  i = node.keys.length - 1',                                   // 9
  '  if node.isLeaf:',                                            // 10
  '    shift keys right to insert in sorted position',            // 11
  '    node.keys.insert(key at correct position)',                 // 12
  '  else:',                                                       // 13
  '    find i such that key > node.keys[i]',                      // 14
  '    if node.children[i+1] is full:',                           // 15
  '      splitChild(node, i+1, node.children[i+1])',              // 16
  '      if key > node.keys[i+1]: i++',                           // 17
  '    insertNonFull(node.children[i+1], key)',                   // 18
  '',                                                              // 19
  'function splitChild(parent, i, child):',                       // 20
  '  newNode = createNode()',                                      // 21
  '  medianKey = child.keys[t-1]',                                // 22
  '  newNode.keys = child.keys[t:]',                              // 23
  '  child.keys = child.keys[:t-1]',                              // 24
  '  if not child.isLeaf:',                                       // 25
  '    newNode.children = child.children[t:]',                    // 26
  '    child.children = child.children[:t]',                      // 27
  '  parent.keys.insert(medianKey at position i)',                 // 28
  '  parent.children.insert(newNode at position i+1)',            // 29
];

function insert(state, key) {
  const steps = [];
  let stepIdx = 0;

  // ws = working state. We mutate this, then createStep clones it each time.
  const ws = cloneState(state);
  const { t } = ws;

  function emit(params) {
    steps.push(createStep({ stepIndex: stepIdx++, state: ws, ...params }));
  }

  emit({
    action:      ACTIONS.INITIAL_STATE,
    explanation: `Inserting key ${key} into the B-tree (t=${t}, max keys per node = ${2 * t - 1}).`,
    pseudocodeLine: 0,
    variables: { key, t },
    meta: { phase: 'descend', depth: 0 },
  });

  // If root is full we have to split it first --, this is the only time
  // the tree can grow taller. The new root starts with 0 keys, the old
  // root becomes its sole child, then we split that child.
  const root = ws.nodes[ws.rootId];
  if (isFull(root, t)) {
    emit({
      action:     ACTIONS.OVERFLOW_DETECTED,
      isKeyStep:  true,
      highlights: { nodes: [{ nodeId: ws.rootId, role: NODE_ROLES.OVERFLOW }] },
      explanation: `The root is full (${root.keys.length} keys = 2t-1). Root splits are special: we create a new root above the current one. This is the only way a B-tree grows taller.`,
      pseudocodeLine: 1,
      variables: { node: ws.rootId, key, t },
      meta: { phase: 'act', reason: 'overflow', depth: 0 },
    });

    const oldRootId = ws.rootId;
    const newRootId = generateId('node');

    ws.nodes[newRootId] = {
      id:       newRootId,
      keys:     [],
      children: [oldRootId],
      isLeaf:   false,
      parentId: null,
    };
    ws.nodes[oldRootId].parentId = newRootId;
    ws.rootId = newRootId;

    emit({
      action:     ACTIONS.SPLIT_ROOT,
      isKeyStep:  true,
      highlights: {
        nodes: [
          { nodeId: newRootId, role: NODE_ROLES.PARENT },
          { nodeId: oldRootId, role: NODE_ROLES.OVERFLOW },
        ],
      },
      explanation: `New root created. It has no keys yet --, it will receive the median key from the split of the old root.`,
      pseudocodeLine: 2,
      variables: { node: newRootId, key, t },
      meta: { phase: 'act', depth: 0 },
    });

    splitChild(ws, newRootId, 0, steps, stepIdx, emit);
  }

  insertNonFull(ws, ws.rootId, key, 0, steps, emit);

  emit({
    action:     ACTIONS.OPERATION_COMPLETE,
    isKeyStep:  true,
    explanation: `Key ${key} has been inserted. All B-tree invariants hold.`,
    pseudocodeLine: 6,
    variables: { key, t },
    meta: { phase: 'unwind' },
  });

  return steps;
}

// Recursively inserts into a node that is guaranteed to NOT be full.
// Splits any full child before descending into it (proactive).
function insertNonFull(ws, nodeId, key, depth, steps, emit) {
  const node = () => ws.nodes[nodeId];

  emit({
    action:     ACTIONS.SEARCH_ENTER_NODE,
    highlights: { nodes: [{ nodeId, role: NODE_ROLES.ACTIVE }] },
    explanation: depth === 0
      ? `Starting at the root. We'll find the correct leaf by comparing and descending.`
      : `Now at depth ${depth}. ${node().isLeaf ? 'This is a leaf --, we insert here.' : 'Internal node --, finding the right child.'}`,
    pseudocodeLine: 8,
    variables: { node: nodeId, key, t: ws.t },
    meta: { phase: 'descend', depth },
  });

  if (node().isLeaf) {
    // Find the sorted insertion position
    let pos = 0;
    while (pos < node().keys.length && key > node().keys[pos]) pos++;

    if (node().keys.length > 0) {
      emit({
        action:     ACTIONS.INSERT_SHIFT_KEYS,
        highlights: {
          nodes: [{ nodeId, role: NODE_ROLES.ACTIVE }],
          keys:  node().keys
            .slice(pos)
            .map((_, i) => ({ nodeId, keyIndex: pos + i, role: KEY_ROLES.INSERTING })),
        },
        explanation: pos < node().keys.length
          ? `Keys at positions ${pos}+ shift right one slot to make room for ${key}.`
          : `${key} is larger than all keys here --, appending at the end.`,
        pseudocodeLine: 11,
        variables: { node: nodeId, key, keyIndex: pos, t: ws.t },
        meta: { phase: 'act', depth },
      });
    }

    node().keys.splice(pos, 0, key);

    emit({
      action:     ACTIONS.INSERT_INTO_LEAF,
      isKeyStep:  true,
      highlights: {
        nodes: [{ nodeId, role: NODE_ROLES.ACTIVE }],
        keys:  [{ nodeId, keyIndex: pos, role: KEY_ROLES.INSERTING }],
      },
      explanation: `Key ${key} inserted at index ${pos} in this leaf. No split needed --, node has ${node().keys.length} key(s) ≤ ${2 * ws.t - 1}.`,
      pseudocodeLine: 12,
      variables: { node: nodeId, key, keyIndex: pos, t: ws.t },
      meta: { phase: 'act', depth },
    });
    return;
  }

  // Internal node: find which child to descend into
  let i = node().keys.length - 1;
  while (i >= 0 && key < node().keys[i]) i--;
  i++; // i is now the index of the child we'll descend into

  emit({
    action:     ACTIONS.SEARCH_COMPARE_KEY,
    highlights: {
      nodes: [{ nodeId, role: NODE_ROLES.ACTIVE }],
      keys: i > 0 ? [{ nodeId, keyIndex: i - 1, role: KEY_ROLES.COMPARING }] : [],
    },
    explanation: i === 0
      ? `${key} is less than all keys here. We descend into the leftmost child.`
      : i === node().keys.length
        ? `${key} is greater than all keys here. We descend into the rightmost child.`
        : `${key} falls between keys[${i - 1}]=${node().keys[i - 1]} and keys[${i}]=${node().keys[i]}. Descend into child ${i}.`,
    pseudocodeLine: 14,
    variables: { node: nodeId, key, childIndex: i, t: ws.t },
    meta: { phase: 'descend', depth },
  });

  const childId = node().children[i];
  const child = ws.nodes[childId];

  if (isFull(child, ws.t)) {
    // Proactive split: handle the full child before descending into it
    emit({
      action:     ACTIONS.OVERFLOW_DETECTED,
      isKeyStep:  true,
      highlights: {
        nodes: [
          { nodeId, role: NODE_ROLES.PARENT },
          { nodeId: childId, role: NODE_ROLES.OVERFLOW },
        ],
      },
      explanation: `Child node has ${child.keys.length} keys = 2t-1 --, it's full. We split it before descending so we never need to backtrack.`,
      pseudocodeLine: 15,
      variables: { node: childId, parent: nodeId, key, t: ws.t },
      meta: { phase: 'act', reason: 'overflow', depth: depth + 1 },
    });

    splitChild(ws, nodeId, i, steps, null, emit);

    // After the split, node now has a new key at position i.
    // Check if we need to descend into the right half instead.
    if (key > node().keys[i]) {
      i++;
      emit({
        action:     ACTIONS.SEARCH_DESCEND,
        highlights: {
          nodes: [{ nodeId, role: NODE_ROLES.PARENT }],
          edges: [{ fromId: nodeId, toId: node().children[i], role: EDGE_ROLES.PATH }],
        },
        explanation: `After split, ${key} > new separator key ${node().keys[i - 1]}, so we descend into the right half.`,
        pseudocodeLine: 17,
        variables: { node: nodeId, key, childIndex: i, t: ws.t },
        meta: { phase: 'descend', depth },
      });
    }
  } else {
    emit({
      action:     ACTIONS.SEARCH_DESCEND,
      highlights: {
        nodes: [{ nodeId, role: NODE_ROLES.ACTIVE }],
        edges: [{ fromId: nodeId, toId: childId, role: EDGE_ROLES.PATH }],
      },
      explanation: `Child has ${child.keys.length} key(s) --, not full. Descending.`,
      pseudocodeLine: 18,
      variables: { node: nodeId, key, childIndex: i, t: ws.t },
      meta: { phase: 'descend', depth },
    });
  }

  insertNonFull(ws, node().children[i], key, depth + 1, steps, emit);
}

// Splits ws.nodes[parent.children[childIdx]] in place.
// Left half keeps the original node ID (preserves stable IDs per spec section 4.4).
// Right half gets a new ID. Median goes up to parent.
function splitChild(ws, parentId, childIdx, steps, _ignored, emit) {
  const parent = ws.nodes[parentId];
  const childId = parent.children[childIdx];
  const child   = ws.nodes[childId];
  const t       = ws.t;

  const medianIdx = t - 1;
  const medianKey = child.keys[medianIdx];

  emit({
    action:     ACTIONS.SPLIT_PREPARE,
    highlights: {
      nodes: [
        { nodeId: parentId, role: NODE_ROLES.PARENT },
        { nodeId: childId,  role: NODE_ROLES.OVERFLOW },
      ],
      keys: [{ nodeId: childId, keyIndex: medianIdx, role: KEY_ROLES.MEDIAN }],
    },
    explanation: `Median key is at index ${medianIdx} (value ${medianKey}). Keys to its left stay here; keys to its right move to the new sibling.`,
    pseudocodeLine: 22,
    variables: { node: childId, parent: parentId, medianIndex: medianIdx, key: medianKey, t },
    meta: { phase: 'act', reason: 'overflow', splitFrom: childId },
  });

  // Build the new right-sibling node
  const newId = generateId('node');
  const newNode = {
    id:       newId,
    keys:     child.keys.slice(t),          // keys to the right of median
    children: [],
    isLeaf:   child.isLeaf,
    parentId: parentId,
  };

  if (!child.isLeaf) {
    newNode.children = child.children.slice(t);
    // Update parentId for the moved children
    for (const cid of newNode.children) {
      ws.nodes[cid].parentId = newId;
    }
    child.children = child.children.slice(0, t);
  }

  child.keys = child.keys.slice(0, medianIdx);
  ws.nodes[newId] = newNode;

  emit({
    action:     ACTIONS.SPLIT_EXECUTE,
    isKeyStep:  true,
    highlights: {
      nodes: [
        { nodeId: childId, role: NODE_ROLES.SPLIT_LEFT  },
        { nodeId: newId,   role: NODE_ROLES.SPLIT_RIGHT },
      ],
      keys: [{ nodeId: childId, keyIndex: medianIdx, role: KEY_ROLES.PROMOTING }],
    },
    explanation: `Split: left node keeps [${child.keys}], right node gets [${newNode.keys}]. Median (${medianKey}) will rise to the parent.`,
    pseudocodeLine: 23,
    variables: { node: childId, parent: parentId, medianIndex: medianIdx, key: medianKey, t },
    meta: { phase: 'act', reason: 'overflow', splitFrom: childId },
  });

  // Promote median key into parent
  emit({
    action:     ACTIONS.PROMOTE_KEY,
    isKeyStep:  true,
    highlights: {
      nodes: [
        { nodeId: parentId, role: NODE_ROLES.PARENT },
        { nodeId: childId,  role: NODE_ROLES.SPLIT_LEFT  },
        { nodeId: newId,    role: NODE_ROLES.SPLIT_RIGHT },
      ],
      keys: [{ nodeId: parentId, keyIndex: childIdx, role: KEY_ROLES.PROMOTING }],
    },
    explanation: `Key ${medianKey} is promoted. It will separate [${child.keys}] on the left and [${newNode.keys}] on the right in the parent.`,
    pseudocodeLine: 28,
    variables: { node: parentId, key: medianKey, keyIndex: childIdx, t },
    meta: { phase: 'act', reason: 'overflow' },
  });

  // Insert median into parent's key array and the new node into parent's children
  parent.keys.splice(childIdx, 0, medianKey);
  parent.children.splice(childIdx + 1, 0, newId);

  emit({
    action:     ACTIONS.PROMOTE_INTO_PARENT,
    highlights: {
      nodes: [{ nodeId: parentId, role: NODE_ROLES.ACTIVE }],
      keys:  [{ nodeId: parentId, keyIndex: childIdx, role: KEY_ROLES.INSERTING }],
    },
    explanation: `Parent absorbs key ${medianKey} at index ${childIdx}. It now has ${parent.keys.length} key(s) and ${parent.children.length} children.`,
    pseudocodeLine: 28,
    variables: { node: parentId, key: medianKey, keyIndex: childIdx, t },
    meta: { phase: 'act' },
  });

  emit({
    action:     ACTIONS.EDGE_REROUTE,
    highlights: {
      nodes: [
        { nodeId: childId, role: NODE_ROLES.SPLIT_LEFT  },
        { nodeId: newId,   role: NODE_ROLES.SPLIT_RIGHT },
      ],
      edges: [
        { fromId: parentId, toId: childId, role: EDGE_ROLES.NEW },
        { fromId: parentId, toId: newId,   role: EDGE_ROLES.NEW },
      ],
    },
    explanation: `Child pointers updated. Left child (≤ ${medianKey}) and right child (> ${medianKey}) are now wired to the parent. Split complete.`,
    pseudocodeLine: 29,
    variables: { node: parentId, t },
    meta: { phase: 'act' },
  });
}

module.exports = { insert, splitChild, PSEUDOCODE };