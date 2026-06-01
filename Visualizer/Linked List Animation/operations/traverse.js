/**
 * OPERATION: TRAVERSE
 *
 * Walks the list from head to null, visiting each node.
 * This is the most fundamental operation --, students must understand traversal
 * before they can understand insert/delete.
 */

import { cloneState, createStep } from './shared.js';
import { NODE_ROLES, POINTER_ROLES, ACTIONS } from '../schema/index.js';

// ─── Pseudocode ───────────────────────────────────────────────────────────────
// Each line is a string; steps reference a 0-based index into this array.
// The narrative layer will highlight the active line.

export const PSEUDOCODE = [
  /* 0 */ 'current ← head',
  /* 1 */ 'WHILE current ≠ NULL DO',
  /* 2 */ '    visit(current.value)',
  /* 3 */ '    current ← current.next',
  /* 4 */ 'END WHILE',
];

// ─── Operation ───────────────────────────────────────────────────────────────

/**
 * Produces the full sequence of animation steps for traversing a linked list.
 *
 * @param {ListState} list
 * @returns {Step[]}
 */
export function traverse(list) {
  const steps = [];
  let idx = 0;

  // We never mutate the original; we work on a clone.
  const state = cloneState(list);

  // ── Step 0: Announce the operation ──────────────────────────────────────

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.INITIAL_STATE,
    explanation:  `We are about to traverse the list. Traversal means visiting every node once, starting from the head and following "next" pointers until we reach null. The list currently has ${list.size} node${list.size !== 1 ? 's' : ''}.`,
    nodeHighlights: list.head ? [{ nodeId: list.head, role: NODE_ROLES.HEAD }] : [],
    variables:    { current: null },
    pseudocodeLine: null,
    isKeyStep:    true,
  }));

  // ── Step 1: current ← head ───────────────────────────────────────────────

  if (list.head === null) {
    steps.push(createStep({
      stepIndex: idx++,
      state,
      action:       ACTIONS.SET_CURRENT_TO_HEAD,
      explanation:  'We set current ← head. But head is null --, the list is empty. There are no nodes to visit.',
      nodeHighlights: [],
      variables:    { current: null },
      pseudocodeLine: 0,
      isKeyStep:    true,
    }));

    steps.push(createStep({
      stepIndex: idx++,
      state,
      action:       ACTIONS.OPERATION_COMPLETE,
      explanation:  'Traversal complete. Because the list was empty, we visited 0 nodes.',
      nodeHighlights: [],
      variables:    { current: null },
      pseudocodeLine: 4,
      isKeyStep:    true,
    }));

    return steps;
  }

  const headNode = state.nodes[state.head];
  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.SET_CURRENT_TO_HEAD,
    explanation:  `We set current ← head. "current" is a temporary pointer that we will use to walk through the list. It now points to the head node, which holds the value ${headNode.value}.`,
    nodeHighlights: [{ nodeId: state.head, role: NODE_ROLES.VISITING }],
    variables:    { current: state.head },
    pseudocodeLine: 0,
    isKeyStep:    true,
  }));

  // ── Loop ─────────────────────────────────────────────────────────────────

  let currentId = list.head;
  const visited = new Set();   // cycle guard

  while (currentId !== null) {
    if (visited.has(currentId)) break;
    visited.add(currentId);

    const node = state.nodes[currentId];

    // WHILE condition check (passes --, current ≠ null)
    steps.push(createStep({
      stepIndex: idx++,
      state,
      action:       ACTIONS.CHECK_WHILE_CONDITION,
      explanation:  `Loop condition: is current null? No --, current points to the node with value ${node.value}. We enter the loop body.`,
      nodeHighlights: [{ nodeId: currentId, role: NODE_ROLES.VISITING }],
      variables:    { current: currentId },
      pseudocodeLine: 1,
      isKeyStep:    false,
    }));

    // Visit the node
    steps.push(createStep({
      stepIndex: idx++,
      state,
      action:       ACTIONS.VISIT_NODE,
      explanation:  `We visit this node. Its value is ${node.value}. In a real use-case this is where you would process the value (print it, compare it, accumulate it, etc.).`,
      nodeHighlights: [{ nodeId: currentId, role: NODE_ROLES.FOUND }],
      variables:    { current: currentId },
      pseudocodeLine: 2,
      isKeyStep:    true,
    }));

    // Advance current
    if (node.next !== null) {
      const nextNode = state.nodes[node.next];
      steps.push(createStep({
        stepIndex: idx++,
        state,
        action:       ACTIONS.ADVANCE_CURRENT,
        explanation:  `current ← current.next. We follow the "next" pointer out of this node (value: ${node.value}). "current" now points to the node with value ${nextNode.value}.`,
        nodeHighlights: [
          { nodeId: currentId,  role: NODE_ROLES.DEFAULT },
          { nodeId: node.next,  role: NODE_ROLES.VISITING },
        ],
        pointerHighlights: [
          { fromId: currentId, toId: node.next, role: POINTER_ROLES.TRAVERSING },
        ],
        variables:    { current: node.next },
        pseudocodeLine: 3,
        isKeyStep:    false,
      }));
    } else {
      steps.push(createStep({
        stepIndex: idx++,
        state,
        action:       ACTIONS.ADVANCE_CURRENT_TO_NULL,
        explanation:  `current ← current.next. The current node (value: ${node.value}) is the tail --, its "next" is null. "current" becomes null, which will end the loop.`,
        nodeHighlights: [{ nodeId: currentId, role: NODE_ROLES.TAIL }],
        variables:    { current: null },
        pseudocodeLine: 3,
        isKeyStep:    false,
      }));
    }

    currentId = node.next;
  }

  // WHILE condition check (fails --, current is null, loop exits)
  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.OPERATION_COMPLETE,
    explanation:  `Loop condition: is current null? Yes --, we have reached the end of the list. The WHILE loop exits. Traversal is complete. We visited ${list.size} node${list.size !== 1 ? 's' : ''}.`,
    nodeHighlights: [],
    variables:    { current: null },
    pseudocodeLine: 4,
    isKeyStep:    true,
  }));

  return steps;
}