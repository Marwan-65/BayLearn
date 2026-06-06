
//This file is the core b tree state management,
//it doesnt do anything in the UI only data
// it doesnt generate steps or change input state

const { generateId } = require('./shared');

//create an empty tree with only a root also makes sure t is 2 or more which is the minimum to geta btree

function createTree(t = 2) {
  if (t < 2) throw new Error(`t must be >= 2, got ${t}`);

  const rootId = generateId('root');
  return {
    t,
    rootId,
    nodes: {
      [rootId]: { //empty leaf
        id: rootId,
        keys: [],
        children: [],
        isLeaf: true,
        parentId: null,
      },
    },
  };
}

// ---------- derived property helpers ---
//called frequemtly by the algorithms.


// invariant, checks for if it has the max possible number of keys then its full
function isFull(node, t) {
  return node.keys.length === 2 * t - 1;
}

//invariant, checks if more than max number of keys the overflow, 
// checked when inserting, before we fire the split
function isOverflow(node, t) {
  
  return node.keys.length > 2 * t - 1;
}

//invariant, check if less than minumum number of keys
//checked when deleting, after we merge or borrow
function isUnderflow(node, state) {
  if (node.id === state.rootId) return false; //root is the exception to underflow
  return node.keys.length < state.t - 1;
}

//performs in order traversal to return all keys in sorted order
// used to validate keys are corretcly sorted
function inOrderKeys(state) {
  const result = [];

  function traverse(nodeId) {
    const n = state.nodes[nodeId];
    if (!n) return;
    for (let i = 0; i < n.keys.length; i++) { 
      if (!n.isLeaf) traverse(n.children[i]);//visit children to te left of they key before the key itself
      result.push(n.keys[i]);
    }
    if (!n.isLeaf) {
      traverse(n.children[n.keys.length]);
    }
  }

  traverse(state.rootId);
  return result;
}

//get tree height (number of levels, root = level 1).
function height(state) {
  let h = 0;
  let nodeId = state.rootId;
  while (nodeId) {
    h++;
    const n = state.nodes[nodeId];
    //go down to the left until you hit a leaf and count. it doesnt matter left from right as all leaves are the same level
    if (n.isLeaf) { 
      nodeId = null;
    } else {
      nodeId = n.children[0];
    }
  }
  return h;
}


//validate all the invariants of the btree, returns an array of error strings
function validate(state) {
  const errors = [];
  const { t, rootId, nodes } = state;

  if (!nodes[rootId]) {
    errors.push(`Root node '${rootId}' not in nodes map`);
    return errors; //nothing else to check lol
  }

  //collect leaf depths to check if they are all the same at the end
  //we also check other invariants at the same loop to avoid multiple needless passes
  const leafDepths = [];

  for (const [id, node] of Object.entries(nodes)) {
    //key count
    if (id !== rootId) {
      if (node.keys.length < t - 1) {
        errors.push(
          `Node ${id}: has ${node.keys.length} keys, minimum is t-1=${t - 1}`
        );
      }
    } else {
      //root must have at least 1 key
      if (Object.keys(nodes).length > 1 && node.keys.length < 1) {
        errors.push(`Root ${id}: must have at least 1 key when tree is non-empty`);
      }
    }

    if (node.keys.length > 2 * t - 1) {
      errors.push(
        `Node ${id}: has ${node.keys.length} keys, maximum is 2t-1=${2 * t - 1}`
      );
    }

    //check if keys are sorted withing the node
    for (let i = 0; i < node.keys.length - 1; i++) {
      if (node.keys[i] >= node.keys[i + 1]) {
        errors.push(
          `Node ${id}: keys not strictly sorted at index ${i} (${node.keys[i]} >= ${node.keys[i + 1]})`
        );
      }
    }

    //leaf node and internal node consistencty
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

    //parentId consistency
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

    //children exist and point back correctly
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

    // Collect leaf depths while we are iterating
    if (node.isLeaf) {
      // compute depth by walking up via parentId
      let d = 0;
      let cur = node;
      while (cur.parentId) {
        d++;
        cur = nodes[cur.parentId];
        if (!cur) break; // broken parent chain, already caught above
      }
      leafDepths.push(d);
    }
  }

  //check that all leaves are at the same depth
  if (leafDepths.length > 1) {
    const first = leafDepths[0];
    const bad = leafDepths.filter(d => d !== first);// if any leaf has a different depth than the first leaf, then we report an error. hddueie
    if (bad.length > 0) {
      errors.push(
        `Leaves are not at uniform depth. Expected all at depth ${first}, found: ${[...new Set(leafDepths)].sort().join(', ')}`
      );
    }
  }

  //check that in order traversal is sorted correctly
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