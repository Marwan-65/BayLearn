
 //el file da byet3amel delete operation 3la el btree, w byerga3 array of steps, w kol step byet2aked en el state of the tree after the delete operation is accurately reflected in the step object. w el narrative da reactive, ya3ni ben delete awel 7aga w ba3dein ben fix el underflow if needed, 3la tool ma ben delete, 3la tool ma ben fix, w ba3dein ben emit ROOT_SHRINK law el merge khalas el root empty.
const { ACTIONS, NODE_ROLES, KEY_ROLES, EDGE_ROLES } = require('./constants');
const { generateId, cloneState, createStep } = require('./shared');
// dol el pseudo codes bta3et el delete 3shan el shar7 wl highlights
const PSEUDOCODE = [
  'function delete(key):',                                     // 0
  '  _delete(root, key)',                                      // 1
  '  if root.keys.length == 0 and root has children:',        // 2
  '    root = root.children[0]',                              // 3
  '',                                                          // 4
  'function _delete(node, key):',                             // 5
  '  i = findPosition(node, key)',                            // 6
  '  if key found at node.keys[i]:',                         // 7
  '    if node.isLeaf: remove node.keys[i]',                 // 8
  '    else:',                                                // 9
  '      pred = getPredecessor(node.children[i])',            // 10
  '      node.keys[i] = pred',                               // 11
  '      _delete(node.children[i], pred)',                    // 12
  '  else:',                                                  // 13
  '    _delete(node.children[i], key)',                       // 14
  '  fixUnderflow(node)',                                     // 15
];
//el main function ll delete, by clone el state w by call el recursive delete function w by handle root shrink law lazem, w by emit final step el operation complete
function deleteKey(state, key) {
  const steps = [];
  let stepIdx = 0;

  const ws = cloneState(state);
  const { t } = ws;

  function emit(params) {
    steps.push(createStep({ stepIndex: stepIdx++, state: ws, ...params }));
  }

  emit({
    action:      ACTIONS.INITIAL_STATE,
    explanation: `Deleting key ${key} from the B-tree (t=${t}).`,
    pseudocodeLine: 0,
    variables: { key, t },
    meta: { phase: 'descend', depth: 0 },
  });

  _delete(ws, ws.rootId, key, 0, emit, t);

  // lw el root ba2et empty w liha child, e3mel promote ll child da root el gdida, w delete el root el fadya di mn el working state, w emit step yeb2a root shrink
  const root = ws.nodes[ws.rootId];
  if (root.keys.length === 0 && root.children.length === 1) {
    const newRootId = root.children[0];

    emit({
      action:     ACTIONS.ROOT_SHRINK,
      isKeyStep:  true,
      highlights: {
        nodes: [
          { nodeId: ws.rootId, role: NODE_ROLES.MERGE_SOURCE },
          { nodeId: newRootId, role: NODE_ROLES.ACTIVE },
        ],
      },
      explanation: `Root is now empty after the merge. Its only child is promoted to root. The tree height decreases by 1 --, all leaves are still at the same depth.`,
      pseudocodeLine: 2,
      variables: { t },
      meta: { phase: 'unwind' },
    });

    delete ws.nodes[ws.rootId];
    ws.rootId = newRootId;
    ws.nodes[ws.rootId].parentId = null;
  }

  emit({
    action:     ACTIONS.OPERATION_COMPLETE,
    isKeyStep:  true,
    explanation: `Deletion of key ${key} complete. All B-tree invariants hold.`,
    pseudocodeLine: 1,
    variables: { key, t },
    meta: { phase: 'unwind' },
  });

  return steps;
}

// el function da byet3amel delete 3la el node elly 3ando el key, w law el key mawgood fe leaf node, by remove el key w by shift el keys left, w law el key mawgood fe internal node, by find el in-order predecessor w by replace el key bta3 internal node da bta3 el predecessor, w ba3dein by call recursive delete 3la el child node da 3shan y remove el predecessor mn el leaf, w ba3dein by check law el recursive delete da5al 7ala underflow fe child node da w law da5al 7ala underflow, by fix el underflow using borrow-left aw borrow-right aw merge.
function _delete(ws, nodeId, key, depth, emit, t) {
  const node = () => ws.nodes[nodeId];

  //dawar 3la el key aw n descend feen
  let i = 0;
  while (i < node().keys.length && key > node().keys[i]) i++;

  const found = i < node().keys.length && node().keys[i] === key;

  emit({
    action:     ACTIONS.SEARCH_ENTER_NODE,
    highlights: {
      nodes: [{ nodeId, role: NODE_ROLES.ACTIVE }],
      keys: found ? [{ nodeId, keyIndex: i, role: KEY_ROLES.COMPARING }] : [],
    },
    explanation: found
      ? `Found key ${key} at index ${i} in this node.`
      : `Key ${key} not in this node --, ${node().isLeaf ? 'not in tree' : `descending into child ${i}`}.`,
    pseudocodeLine: 6,
    variables: { node: nodeId, key, t },
    meta: { phase: 'descend', depth },
  });

  if (found) {
    if (node().isLeaf) {
      // awel case enaha teb2a leaf node
      emit({
        action:     ACTIONS.DELETE_FIND_KEY,
        isKeyStep:  true,
        highlights: {
          nodes: [{ nodeId, role: NODE_ROLES.ACTIVE }],
          keys:  [{ nodeId, keyIndex: i, role: KEY_ROLES.DELETING }],
        },
        explanation: `Key ${key} is in a leaf node. We can remove it directly.`,
        pseudocodeLine: 8,
        variables: { node: nodeId, key, keyIndex: i, t },
        meta: { phase: 'act', reason: 'found', depth },
      });

      node().keys.splice(i, 1);

      emit({
        action:     ACTIONS.DELETE_FROM_LEAF,
        highlights: {
          nodes: [{ nodeId, role: NODE_ROLES.ACTIVE }],
        },
        explanation: `Key ${key} removed. Node now has ${node().keys.length} key(s).${node().keys.length > 0 ? ` Keys: [${node().keys}].` : ' Node is empty.'}`,
        pseudocodeLine: 8,
        variables: { node: nodeId, key, t },
        meta: { phase: 'act', depth },
      });

      if (node().keys.length > 0) {
        emit({
          action:     ACTIONS.DELETE_SHIFT_KEYS,
          highlights: { nodes: [{ nodeId, role: NODE_ROLES.ACTIVE }] },
          explanation: `Remaining keys shift left to close the gap.`,
          pseudocodeLine: 8,
          variables: { node: nodeId, t },
          meta: { phase: 'act', depth },
        });
      }

    } else {
      // tany case enaha tev2a internal node, fa lazm n find el in-order predecessor w n replace el key bta3 el internal node da bta3 el predecessor, w ba3dein n call recursive delete 3la el child node da 3shan y remove el predecessor mn el leaf, w ba3dein n check law el recursive delete da5al 7ala underflow fe child node da w law da5al 7ala underflow, n fix el underflow using borrow-left aw borrow-right aw merge.
      emit({
        action:     ACTIONS.DELETE_FIND_KEY,
        isKeyStep:  true,
        highlights: {
          nodes: [{ nodeId, role: NODE_ROLES.ACTIVE }],
          keys:  [{ nodeId, keyIndex: i, role: KEY_ROLES.DELETING }],
        },
        explanation: `Key ${key} is in an internal node. We'll replace it with its in-order predecessor (the largest key in the left subtree), then delete the predecessor from the leaf.`,
        pseudocodeLine: 9,
        variables: { node: nodeId, key, keyIndex: i, t },
        meta: { phase: 'act', reason: 'found', depth },
      });

      emit({
        action:     ACTIONS.FIND_PREDECESSOR,
        highlights: {
          nodes: [{ nodeId, role: NODE_ROLES.PARENT }],
          edges: [{ fromId: nodeId, toId: node().children[i], role: EDGE_ROLES.PATH }],
        },
        explanation: `Descending into the left subtree to find the in-order predecessor of ${key}.`,
        pseudocodeLine: 10,
        variables: { node: nodeId, key, childIndex: i, t },
        meta: { phase: 'descend', depth },
      });

      const pred = getPredecessorKey(ws, node().children[i]);

      emit({
        action:     ACTIONS.REPLACE_WITH_PRED,
        isKeyStep:  true,
        highlights: {
          nodes: [{ nodeId, role: NODE_ROLES.ACTIVE }],
          keys:  [{ nodeId, keyIndex: i, role: KEY_ROLES.PREDECESSOR }],
        },
        explanation: `In-order predecessor is ${pred}. Replace ${key} with ${pred} at index ${i}, then delete ${pred} from the leaf.`,
        pseudocodeLine: 11,
        variables: { node: nodeId, key: pred, predecessor: pred, keyIndex: i, t },
        meta: { phase: 'act', depth },
      });

      node().keys[i] = pred;

      // Recursively delete the predecessor from the left subtree
      _delete(ws, node().children[i], pred, depth + 1, emit, t);

      // sala7 ay underflow wesel ll left child
      const leftChildId = node().children[i];
      if (isUnderflowing(ws, leftChildId)) {
        fixUnderflow(ws, nodeId, i, emit, t);
      }
    }

  } else {
    // talet case en el key msh fl node di, me7tageen n descend
    if (node().isLeaf) {
      // Key is simply not in the tree --, nothing to do
      emit({
        action:     ACTIONS.SEARCH_NOT_FOUND,
        isKeyStep:  true,
        highlights: { nodes: [{ nodeId, role: NODE_ROLES.ACTIVE }] },
        explanation: `Key ${key} is not in the tree. Reached a leaf without finding it.`,
        pseudocodeLine: 13,
        variables: { node: nodeId, key, t },
        meta: { phase: 'act', reason: 'not-found', depth },
      });
      return;
    }

    const childId = node().children[i];

    emit({
      action:     ACTIONS.SEARCH_DESCEND,
      highlights: {
        nodes: [{ nodeId, role: NODE_ROLES.ACTIVE }],
        edges: [{ fromId: nodeId, toId: childId, role: EDGE_ROLES.PATH }],
      },
      explanation: `Key ${key} is not here --, descending into child ${i}.`,
      pseudocodeLine: 14,
      variables: { node: nodeId, key, childIndex: i, t },
      meta: { phase: 'descend', depth },
    });

    _delete(ws, childId, key, depth + 1, emit, t);

    // sala7 el underflow lw el recursive delete left our child short
    if (isUnderflowing(ws, node().children[i])) {
      fixUnderflow(ws, nodeId, i, emit, t);
    }
  }
}

//byragga3 el laregst key fl subtree rooted at nodeId (rightmost leaf).
function getPredecessorKey(ws, nodeId) {
  let n = ws.nodes[nodeId];
  while (!n.isLeaf) {
    n = ws.nodes[n.children[n.children.length - 1]];
  }
  return n.keys[n.keys.length - 1];
}

function isUnderflowing(ws, nodeId) {
  const n = ws.nodes[nodeId];
  if (!n) return false;
  if (nodeId === ws.rootId) return false;
  return n.keys.length < ws.t - 1;
}


//by fix el underflowing child node da, by check law fe sibling yeb2a y2dar yeb2a source fe borrow, w law fe sibling yeb2a y2dar yeb2a source fe borrow, w law mafesh siblings y2dar yeb2a source fe borrow, by merge ma3 wa7ed mn el siblings, w ba3dein by emit steps accordingly.
function fixUnderflow(ws, parentId, childIdx, emit, t) {
  const parent   = () => ws.nodes[parentId];
  const childId  = parent().children[childIdx];
  const child    = () => ws.nodes[childId];

  emit({
    action:     ACTIONS.UNDERFLOW_DETECTED,
    highlights: {
      nodes: [
        { nodeId: parentId, role: NODE_ROLES.PARENT   },
        { nodeId: childId,  role: NODE_ROLES.UNDERFLOW },
      ],
    },
    explanation: `Node has ${child().keys.length} key(s), below the minimum t-1=${t - 1}. We must fix this before returning.`,
    pseudocodeLine: 15,
    variables: { node: childId, parent: parentId, t },
    meta: { phase: 'unwind', reason: 'underflow' },
  });

  const leftSibId  = childIdx > 0
    ? parent().children[childIdx - 1]
    : null;
  const rightSibId = childIdx < parent().children.length - 1
    ? parent().children[childIdx + 1]
    : null;

  const canBorrowLeft  = leftSibId  && ws.nodes[leftSibId].keys.length  >= t;
  const canBorrowRight = rightSibId && ws.nodes[rightSibId].keys.length >= t;

  if (canBorrowLeft) {
    const leftSib = () => ws.nodes[leftSibId];
    const sepIdx = childIdx - 1; // separator key index fl parent

    emit({
      action:     ACTIONS.FIX_CHOOSE_STRATEGY,
      highlights: {
        nodes: [
          { nodeId: childId,  role: NODE_ROLES.UNDERFLOW    },
          { nodeId: leftSibId, role: NODE_ROLES.SIBLING_LEFT },
        ],
        keys: [{ nodeId: parentId, keyIndex: sepIdx, role: KEY_ROLES.SEPARATOR }],
      },
      explanation: `Left sibling has ${leftSib().keys.length} keys > t-1=${t - 1}. It can spare one. We'll rotate: sibling's rightmost key rises to parent, parent's separator descends to us.`,
      pseudocodeLine: 15,
      variables: { node: childId, leftSibling: leftSibId, parent: parentId, t },
      meta: { phase: 'unwind', reason: 'rotate' },
    });

    emit({
      action:     ACTIONS.BORROW_LEFT_PREPARE,
      isKeyStep:  true,
      highlights: {
        nodes: [
          { nodeId: childId,  role: NODE_ROLES.ACTIVE      },
          { nodeId: leftSibId, role: NODE_ROLES.SIBLING_LEFT },
          { nodeId: parentId, role: NODE_ROLES.PARENT       },
        ],
        keys: [
          { nodeId: leftSibId, keyIndex: leftSib().keys.length - 1, role: KEY_ROLES.SEPARATOR },
          { nodeId: parentId,  keyIndex: sepIdx, role: KEY_ROLES.SEPARATOR },
        ],
      },
      explanation: `Three-way rotation: (1) sibling's key ${leftSib().keys[leftSib().keys.length - 1]} rises to parent, (2) parent's separator ${parent().keys[sepIdx]} descends to us${!child().isLeaf ? ", (3) sibling's rightmost child re-homed to us" : ''}.`,
      pseudocodeLine: 15,
      variables: { node: childId, leftSibling: leftSibId, parent: parentId, t },
      meta: { phase: 'unwind', reason: 'rotate' },
    });

    // e3mel el borrow left rotation yeee
    const promotedKey  = leftSib().keys.pop();
    const separatorKey = parent().keys[sepIdx];
    parent().keys[sepIdx] = promotedKey;
    child().keys.unshift(separatorKey);

    if (!child().isLeaf) {
      const movedChildId = leftSib().children.pop();
      child().children.unshift(movedChildId);
      ws.nodes[movedChildId].parentId = childId;
    }

    emit({
      action:     ACTIONS.BORROW_LEFT_ROTATE,
      isKeyStep:  true,
      highlights: {
        nodes: [
          { nodeId: childId,  role: NODE_ROLES.ACTIVE      },
          { nodeId: leftSibId, role: NODE_ROLES.SIBLING_LEFT },
          { nodeId: parentId, role: NODE_ROLES.PARENT       },
        ],
        keys: [{ nodeId: childId, keyIndex: 0, role: KEY_ROLES.INSERTING }],
      },
      explanation: `Rotation complete. Separator ${separatorKey} is now in our node. Sibling's key ${promotedKey} is the new separator. All order invariants preserved.`,
      pseudocodeLine: 15,
      variables: { node: childId, leftSibling: leftSibId, parent: parentId, t },
      meta: { phase: 'unwind', reason: 'rotate' },
    });

    if (!child().isLeaf) {
      emit({
        action:     ACTIONS.EDGE_REROUTE,
        highlights: {
          edges: [{ fromId: childId, toId: child().children[0], role: EDGE_ROLES.REROUTING }],
        },
        explanation: `Sibling's rightmost subtree is re-assigned as our leftmost child. It contains keys in the range (${promotedKey}, ${separatorKey}).`,
        pseudocodeLine: 15,
        variables: { node: childId, t },
        meta: { phase: 'unwind' },
      });
    }

  } else if (canBorrowRight) {
    const rightSib = () => ws.nodes[rightSibId];
    const sepIdx = childIdx; // separator mabeen el child wl right sibling

    emit({
      action:     ACTIONS.FIX_CHOOSE_STRATEGY,
      highlights: {
        nodes: [
          { nodeId: childId,   role: NODE_ROLES.UNDERFLOW     },
          { nodeId: rightSibId, role: NODE_ROLES.SIBLING_RIGHT },
        ],
        keys: [{ nodeId: parentId, keyIndex: sepIdx, role: KEY_ROLES.SEPARATOR }],
      },
      explanation: `Right sibling has ${rightSib().keys.length} keys > t-1=${t - 1}. Rotating: sibling's leftmost key rises to parent, parent's separator descends to us.`,
      pseudocodeLine: 15,
      variables: { node: childId, rightSibling: rightSibId, parent: parentId, t },
      meta: { phase: 'unwind', reason: 'rotate' },
    });

    emit({
      action:     ACTIONS.BORROW_RIGHT_PREPARE,
      isKeyStep:  true,
      highlights: {
        nodes: [
          { nodeId: childId,   role: NODE_ROLES.ACTIVE        },
          { nodeId: rightSibId, role: NODE_ROLES.SIBLING_RIGHT },
          { nodeId: parentId,  role: NODE_ROLES.PARENT        },
        ],
        keys: [
          { nodeId: rightSibId, keyIndex: 0, role: KEY_ROLES.SEPARATOR },
          { nodeId: parentId,   keyIndex: sepIdx, role: KEY_ROLES.SEPARATOR },
        ],
      },
      explanation: `Rotating right: sibling's key ${rightSib().keys[0]} rises to parent, parent's separator ${parent().keys[sepIdx]} comes down to us.`,
      pseudocodeLine: 15,
      variables: { node: childId, rightSibling: rightSibId, parent: parentId, t },
      meta: { phase: 'unwind', reason: 'rotate' },
    });

    const promotedKey  = rightSib().keys.shift();
    const separatorKey = parent().keys[sepIdx];
    parent().keys[sepIdx] = promotedKey;
    child().keys.push(separatorKey);

    if (!child().isLeaf) {
      const movedChildId = rightSib().children.shift();
      child().children.push(movedChildId);
      ws.nodes[movedChildId].parentId = childId;
    }

    emit({
      action:     ACTIONS.BORROW_RIGHT_ROTATE,
      isKeyStep:  true,
      highlights: {
        nodes: [
          { nodeId: childId,   role: NODE_ROLES.ACTIVE        },
          { nodeId: rightSibId, role: NODE_ROLES.SIBLING_RIGHT },
          { nodeId: parentId,  role: NODE_ROLES.PARENT        },
        ],
        keys: [{ nodeId: childId, keyIndex: child().keys.length - 1, role: KEY_ROLES.INSERTING }],
      },
      explanation: `Rotation complete. Separator ${separatorKey} joined our node. Sibling's key ${promotedKey} is the new separator. Order preserved.`,
      pseudocodeLine: 15,
      variables: { node: childId, rightSibling: rightSibId, parent: parentId, t },
      meta: { phase: 'unwind', reason: 'rotate' },
    });

    if (!child().isLeaf) {
      emit({
        action:     ACTIONS.EDGE_REROUTE,
        highlights: {
          edges: [{ fromId: childId, toId: child().children[child().children.length - 1], role: EDGE_ROLES.REROUTING }],
        },
        explanation: `Sibling's leftmost subtree re-assigned as our rightmost child.`,
        pseudocodeLine: 15,
        variables: { node: childId, t },
        meta: { phase: 'unwind' },
      });
    }

  } else {

    // mafeesh ay sibling ye2dar yeb2a source fe borrow, lazm n merge. law fe left sibling, n merge ma3ah, law mafesh left sibling bas fe right sibling, n merge ma3ah. el merge da by merge el child da ma3 wa7ed mn el siblings, w by pull separator down w by absorb keys w by rehome children law internal, w ba3dein by delete el separator wl sibling el merged from mn el parent, w ba3dein by emit steps accordingly.
    if (leftSibId) {
      mergeNodes(ws, parentId, childIdx - 1, emit, t); // merge left sib with child
    } else {
      mergeNodes(ws, parentId, childIdx, emit, t); // merge child with right sib
    }
  }
}


// merge el parent key w el right sibling ma3 el left sibling, w ba3dein delete el right sibling w el separator mn el parent, w ba3dein emit steps accordingly.
function mergeNodes(ws, parentId, leftIdx, emit, t) {
  const parent   = () => ws.nodes[parentId];
  const leftId   = parent().children[leftIdx];
  const rightId  = parent().children[leftIdx + 1];
  const left     = () => ws.nodes[leftId];
  const right    = () => ws.nodes[rightId];
  const sepKey   = parent().keys[leftIdx];

  emit({
    action:     ACTIONS.FIX_CHOOSE_STRATEGY,
    highlights: {
      nodes: [
        { nodeId: leftId,   role: NODE_ROLES.MERGE_TARGET },
        { nodeId: rightId,  role: NODE_ROLES.MERGE_SOURCE },
        { nodeId: parentId, role: NODE_ROLES.PARENT       },
      ],
      keys: [{ nodeId: parentId, keyIndex: leftIdx, role: KEY_ROLES.SEPARATOR }],
    },
    explanation: `Neither sibling can spare a key --, both have exactly t-1=${t - 1} keys. Merging.`,
    pseudocodeLine: 15,
    variables: { node: leftId, parent: parentId, t },
    meta: { phase: 'unwind', reason: 'merge' },
  });

  emit({
    action:     ACTIONS.MERGE_PREPARE,
    isKeyStep:  true,
    highlights: {
      nodes: [
        { nodeId: leftId,   role: NODE_ROLES.MERGE_TARGET },
        { nodeId: rightId,  role: NODE_ROLES.MERGE_SOURCE },
        { nodeId: parentId, role: NODE_ROLES.PARENT       },
      ],
      keys: [{ nodeId: parentId, keyIndex: leftIdx, role: KEY_ROLES.SEPARATOR }],
    },
    explanation: `Merge: [${left().keys}] + separator ${sepKey} + [${right().keys}] → [${[...left().keys, sepKey, ...right().keys]}]. This gives exactly 2(t-1)+1 = ${2 * t - 1} keys --, the maximum.`,
    pseudocodeLine: 15,
    variables: { node: leftId, parent: parentId, t },
    meta: { phase: 'unwind', reason: 'merge', mergeLeft: leftId, mergeRight: rightId },
  });

  // Pull separator down into left node
  left().keys.push(sepKey);

  emit({
    action:     ACTIONS.MERGE_PULL_SEPARATOR,
    highlights: {
      nodes: [
        { nodeId: leftId,   role: NODE_ROLES.MERGE_TARGET },
        { nodeId: parentId, role: NODE_ROLES.PARENT       },
      ],
      keys: [{ nodeId: leftId, keyIndex: left().keys.length - 1, role: KEY_ROLES.SEPARATOR }],
    },
    explanation: `Separator ${sepKey} descends from parent into the left node.`,
    pseudocodeLine: 15,
    variables: { node: leftId, key: sepKey, t },
    meta: { phase: 'unwind', mergeLeft: leftId, mergeRight: rightId },
  });

  // Absorb right node's keys
  const rightKeys = [...right().keys];
  for (const k of rightKeys) left().keys.push(k);

  emit({
    action:     ACTIONS.MERGE_ABSORB_KEYS,
    isKeyStep:  true,
    highlights: {
      nodes: [
        { nodeId: leftId,  role: NODE_ROLES.MERGE_TARGET },
        { nodeId: rightId, role: NODE_ROLES.MERGE_SOURCE },
      ],
    },
    explanation: `Right node's keys [${rightKeys}] move into the left node. Left node now has [${left().keys}].`,
    pseudocodeLine: 15,
    variables: { node: leftId, t },
    meta: { phase: 'unwind', mergeLeft: leftId, mergeRight: rightId },
  });

  // Absorb right node's children if internal
  if (!right().isLeaf) {
    for (const cid of right().children) {
      left().children.push(cid);
      ws.nodes[cid].parentId = leftId;
    }

    emit({
      action:     ACTIONS.MERGE_ABSORB_CHILDREN,
      highlights: {
        nodes: [{ nodeId: leftId, role: NODE_ROLES.MERGE_TARGET }],
        edges: right().children.map(cid => ({ fromId: leftId, toId: cid, role: EDGE_ROLES.REROUTING })),
      },
      explanation: `Right node's ${right().children.length} child pointer(s) re-homed to the merged node.`,
      pseudocodeLine: 15,
      variables: { node: leftId, t },
      meta: { phase: 'unwind', mergeLeft: leftId, mergeRight: rightId },
    });
  }

  // Remove the right node
  delete ws.nodes[rightId];

  emit({
    action:     ACTIONS.MERGE_REMOVE_NODE,
    isKeyStep:  true,
    highlights: {
      nodes: [{ nodeId: leftId, role: NODE_ROLES.MERGE_TARGET }],
    },
    explanation: `Right node dissolved. It no longer exists in the tree.`,
    pseudocodeLine: 15,
    variables: { node: leftId, t },
    meta: { phase: 'unwind', mergeLeft: leftId, mergeRight: rightId },
  });

  // update el parent, sheel el separator key wl right child pointer
  parent().keys.splice(leftIdx, 1);
  parent().children.splice(leftIdx + 1, 1);

  emit({
    action:     ACTIONS.MERGE_UPDATE_PARENT,
    highlights: {
      nodes: [{ nodeId: parentId, role: NODE_ROLES.PARENT }],
    },
    explanation: `Parent loses separator key ${sepKey} and right child pointer. Parent now has ${parent().keys.length} key(s) and ${parent().children.length} child pointer(s).${parent().keys.length === 0 && parentId === ws.rootId ? ' Root is now empty --, a root shrink is about to occur.' : ''}`,
    pseudocodeLine: 15,
    variables: { node: parentId, t },
    meta: { phase: 'unwind' },
  });
}

module.exports = { deleteKey, PSEUDOCODE };