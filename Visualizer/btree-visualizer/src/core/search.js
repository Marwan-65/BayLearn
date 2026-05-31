// Search operation. Returns Step[] --, never mutates the input state.
//
// Pseudocode indices match spec section 5.1 so pseudocodeLine values
// stay in sync with what the narrative layer will render.

const { ACTIONS, NODE_ROLES, KEY_ROLES, EDGE_ROLES } = require('./constants');
const { createStep } = require('./shared');

const PSEUDOCODE = [
  'function search(node, key):',           // 0
  '  for i = 0 to node.keys.length - 1:', // 1
  '    if key == node.keys[i]:',           // 2
  '      return (node, i)',                // 3
  '    if key < node.keys[i]:',            // 4
  '      if node.isLeaf: return NOT_FOUND',// 5
  '      return search(node.children[i], key)', // 6
  '  if node.isLeaf: return NOT_FOUND',   // 7
  '  return search(node.children[node.keys.length], key)', // 8
];

function search(state, targetKey) {
  const steps = [];
  let idx = 0;

  // State never changes during search so we reuse it for every step.
  // createStep deep-clones it internally.

  steps.push(createStep({
    stepIndex: idx++,
    action:    ACTIONS.INITIAL_STATE,
    state,
    explanation: `Searching for key ${targetKey}. We start at the root and compare keys left to right, descending into the appropriate child subtree at each level.`,
    pseudocodeLine: 0,
    variables: { key: targetKey, t: state.t },
    meta: { phase: 'descend', depth: 0 },
  }));

  // Track the path we've descended so we can highlight those edges on each step
  const edgePath = []; // [{ fromId, toId }]

  function visit(nodeId, depth) {
    const node = state.nodes[nodeId];
    if (!node) return false;

    steps.push(createStep({
      stepIndex: idx++,
      action:    ACTIONS.SEARCH_ENTER_NODE,
      state,
      highlights: {
        nodes: [{ nodeId, role: NODE_ROLES.ACTIVE }],
        edges: edgePath.map(e => ({ ...e, role: EDGE_ROLES.PATH })),
      },
      explanation: depth === 0
        ? 'We begin at the root. Every search starts here regardless of tree depth.'
        : `Now at depth ${depth}. This node is ${node.isLeaf ? 'a leaf --, no children to descend into' : 'an internal node'}.`,
      pseudocodeLine: 0,
      variables: { node: nodeId, key: targetKey, t: state.t },
      meta: { phase: 'descend', depth },
    }));

    for (let i = 0; i < node.keys.length; i++) {
      const k = node.keys[i];

      let compareExplanation;
      if (k === targetKey) {
        compareExplanation = `Is ${targetKey} == ${k}? YES --, found!`;
      } else if (targetKey < k) {
        compareExplanation = `Is ${targetKey} == ${k}? No. Is ${targetKey} < ${k}? Yes --, ${targetKey} must be in the subtree to the left of ${k}.`;
      } else {
        compareExplanation = `Is ${targetKey} == ${k}? No. Is ${targetKey} < ${k}? No --, ${targetKey} is greater, continue rightward.`;
      }

      steps.push(createStep({
        stepIndex: idx++,
        action:    ACTIONS.SEARCH_COMPARE_KEY,
        state,
        highlights: {
          nodes: [{ nodeId, role: NODE_ROLES.ACTIVE }],
          keys:  [{ nodeId, keyIndex: i, role: KEY_ROLES.COMPARING }],
          edges: edgePath.map(e => ({ ...e, role: EDGE_ROLES.PATH })),
        },
        explanation:    compareExplanation,
        pseudocodeLine: 2,
        variables: { node: nodeId, key: targetKey, keyIndex: i, t: state.t },
        meta: { phase: 'descend', depth },
      }));

      if (k === targetKey) {
        steps.push(createStep({
          stepIndex:  idx++,
          action:     ACTIONS.SEARCH_FOUND,
          state,
          isKeyStep:  true,
          highlights: {
            nodes: [{ nodeId, role: NODE_ROLES.ACTIVE }],
            keys:  [{ nodeId, keyIndex: i, role: KEY_ROLES.FOUND }],
            edges: edgePath.map(e => ({ ...e, role: EDGE_ROLES.PATH })),
          },
          explanation:    `Search complete. Key ${targetKey} found at depth ${depth}, index ${i}.`,
          pseudocodeLine: 3,
          variables: { node: nodeId, key: targetKey, keyIndex: i, t: state.t },
          meta: { phase: 'act', reason: 'found', depth },
        }));
        return true;
      }

      if (targetKey < k) {
        if (node.isLeaf) {
          steps.push(createStep({
            stepIndex:  idx++,
            action:     ACTIONS.SEARCH_NOT_FOUND,
            state,
            isKeyStep:  true,
            highlights: {
              nodes: [{ nodeId, role: NODE_ROLES.ACTIVE }],
            },
            explanation:    `${targetKey} < ${k} and this is a leaf --, there is no subtree to descend into. Key ${targetKey} is not in the tree.`,
            pseudocodeLine: 5,
            variables: { node: nodeId, key: targetKey, t: state.t },
            meta: { phase: 'act', reason: 'not-found', depth },
          }));
          return false;
        }

        const childId = node.children[i];
        steps.push(createStep({
          stepIndex: idx++,
          action:    ACTIONS.SEARCH_DESCEND,
          state,
          highlights: {
            nodes: [{ nodeId, role: NODE_ROLES.ACTIVE }],
            edges: [
              ...edgePath.map(e => ({ ...e, role: EDGE_ROLES.PATH })),
              { fromId: nodeId, toId: childId, role: EDGE_ROLES.PATH },
            ],
          },
          explanation:    `${targetKey} < ${k}, so we descend through child pointer ${i}. Every key in that subtree is < ${k}.`,
          pseudocodeLine: 6,
          variables: { node: nodeId, key: targetKey, childIndex: i, t: state.t },
          meta: { phase: 'descend', depth },
        }));

        edgePath.push({ fromId: nodeId, toId: childId });
        const found = visit(childId, depth + 1);
        edgePath.pop();
        return found;
      }

      // targetKey > k --, moving right. Emit a step if there are more keys to look at.
      if (i < node.keys.length - 1) {
        steps.push(createStep({
          stepIndex: idx++,
          action:    ACTIONS.SEARCH_GO_RIGHT,
          state,
          highlights: {
            nodes: [{ nodeId, role: NODE_ROLES.ACTIVE }],
            keys:  [{ nodeId, keyIndex: i + 1, role: KEY_ROLES.COMPARING }],
            edges: edgePath.map(e => ({ ...e, role: EDGE_ROLES.PATH })),
          },
          explanation:    `${targetKey} > ${k}, move right to the next key.`,
          pseudocodeLine: 1,
          variables: { node: nodeId, key: targetKey, keyIndex: i + 1, t: state.t },
          meta: { phase: 'descend', depth },
        }));
      }
    }

    // Exhausted all keys --, either leaf (not found) or descend rightmost child
    if (node.isLeaf) {
      steps.push(createStep({
        stepIndex:  idx++,
        action:     ACTIONS.SEARCH_NOT_FOUND,
        state,
        isKeyStep:  true,
        highlights: { nodes: [{ nodeId, role: NODE_ROLES.ACTIVE }] },
        explanation:    `No more keys to compare in this leaf. Key ${targetKey} is not in the tree.`,
        pseudocodeLine: 7,
        variables: { node: nodeId, key: targetKey, t: state.t },
        meta: { phase: 'act', reason: 'not-found', depth },
      }));
      return false;
    }

    const childId = node.children[node.keys.length];
    steps.push(createStep({
      stepIndex: idx++,
      action:    ACTIONS.SEARCH_DESCEND,
      state,
      highlights: {
        nodes: [{ nodeId, role: NODE_ROLES.ACTIVE }],
        edges: [
          ...edgePath.map(e => ({ ...e, role: EDGE_ROLES.PATH })),
          { fromId: nodeId, toId: childId, role: EDGE_ROLES.PATH },
        ],
      },
      explanation:    `${targetKey} is greater than all keys in this node. Descend into the rightmost child.`,
      pseudocodeLine: 8,
      variables: { node: nodeId, key: targetKey, childIndex: node.keys.length, t: state.t },
      meta: { phase: 'descend', depth },
    }));

    edgePath.push({ fromId: nodeId, toId: childId });
    const found = visit(childId, depth + 1);
    edgePath.pop();
    return found;
  }

  visit(state.rootId, 0);
  return steps;
}

module.exports = { search, PSEUDOCODE };