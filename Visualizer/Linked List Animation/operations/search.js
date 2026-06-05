/**
 * OPERATION: SEARCH
 *
 * Walks the list looking for a node whose value equals the target.
 * Returns steps that show each comparison, then either FOUND or NOT_FOUND.
 *
 * Time complexity: O(n) in the worst case (target not present or at tail).
 *
 * Teaching points:
 *   - Linked lists have O(n) search --, no random access, no binary search
 *   - Every node must be inspected in sequence
 *   - Contrast with arrays (O(1) index access) and hash maps (O(1) average)
 */

import { cloneState, createStep } from './shared.js';
import { NODE_ROLES, POINTER_ROLES, ACTIONS } from '../schema/index.js';

// ─── Pseudocode ───────────────────────────────────────────────────────────────

export const PSEUDOCODE = [
  /* 0 */ 'current ← head',
  /* 1 */ 'index ← 0',
  /* 2 */ 'WHILE current ≠ NULL DO',
  /* 3 */ '    IF current.value = target THEN',
  /* 4 */ '        RETURN index   (found!)',
  /* 5 */ '    END IF',
  /* 6 */ '    current ← current.next',
  /* 7 */ '    index ← index + 1',
  /* 8 */ 'END WHILE',
  /* 9 */ 'RETURN −1   (not found)',
];

// ─── Operation ───────────────────────────────────────────────────────────────

/**
 * Produces steps for a linear search through the list.
 *
 * @param {ListState} list
 * @param {*}         target  - The value to search for
 * @returns {Step[]}
 */
export function searchByValue(list, target) {
  const steps = [];
  let idx = 0;
  const state = cloneState(list);

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.INITIAL_STATE,
    explanation:  `We are searching for the value ${target}. In a linked list we have no choice but to start at the head and check each node one by one --, this is a linear search, O(n) in the worst case.`,
    nodeHighlights: state.head ? [{ nodeId: state.head, role: NODE_ROLES.HEAD }] : [],
    variables:    { current: null },
    pseudocodeLine: null,
    isKeyStep:    true,
  }));

  // Guard: empty list
  if (state.head === null) {
    steps.push(createStep({
      stepIndex: idx++,
      state,
      action:       ACTIONS.VALUE_NOT_FOUND,
      explanation:  `The list is empty. The value ${target} cannot be present. Returning −1.`,
      nodeHighlights: [],
      variables:    { current: null },
      pseudocodeLine: 9,
      isKeyStep:    true,
    }));
    return steps;
  }

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.SET_CURRENT_TO_HEAD,
    explanation:  `current ← head. We begin at the head node (value: ${state.nodes[state.head].value}). We also track an index counter so we can return the position if we find the target.`,
    nodeHighlights: [{ nodeId: state.head, role: NODE_ROLES.VISITING }],
    variables:    { current: state.head, index: 0 },
    pseudocodeLine: 0,
    isKeyStep:    true,
  }));

  let currentId = list.head;
  let position  = 0;
  const visited = new Set();

  while (currentId !== null) {
    if (visited.has(currentId)) break;
    visited.add(currentId);

    const node = state.nodes[currentId];
    const isMatch = node.value === target;

    // WHILE condition check
    steps.push(createStep({
      stepIndex: idx++,
      state,
      action:       ACTIONS.CHECK_WHILE_CONDITION,
      explanation:  `current ≠ null --, we are at index ${position} (value: ${node.value}). We check if this is our target.`,
      nodeHighlights: [{ nodeId: currentId, role: NODE_ROLES.VISITING }],
      variables:    { current: currentId, index: position },
      pseudocodeLine: 2,
      isKeyStep:    false,
    }));

    // Comparison
    steps.push(createStep({
      stepIndex: idx++,
      state,
      action:       ACTIONS.COMPARE_VALUE,
      explanation:  `Is current.value (${node.value}) === ${target}? ${isMatch ? '✅ Yes! We found it.' : `❌ No. We move on.`}`,
      nodeHighlights: [{ nodeId: currentId, role: isMatch ? NODE_ROLES.FOUND : NODE_ROLES.COMPARING }],
      variables:    { current: currentId, index: position },
      pseudocodeLine: 3,
      isKeyStep:    isMatch,
    }));

    if (isMatch) {
      steps.push(createStep({
        stepIndex: idx++,
        state,
        action:       ACTIONS.VALUE_FOUND,
        explanation:  `Found! The value ${target} is at index ${position}. We return ${position}. The search took O(${position + 1}) comparisons.`,
        nodeHighlights: [{ nodeId: currentId, role: NODE_ROLES.FOUND }],
        variables:    { current: currentId, index: position },
        pseudocodeLine: 4,
        isKeyStep:    true,
      }));
      return steps;
    }

    // Advance
    if (node.next !== null) {
      const nextNode = state.nodes[node.next];
      steps.push(createStep({
        stepIndex: idx++,
        state,
        action:       ACTIONS.ADVANCE_CURRENT,
        explanation:  `current ← current.next. Moving from value ${node.value} to value ${nextNode.value} (index ${position + 1}).`,
        nodeHighlights: [
          { nodeId: currentId, role: NODE_ROLES.DEFAULT },
          { nodeId: node.next,  role: NODE_ROLES.VISITING },
        ],
        pointerHighlights: [
          { fromId: currentId, toId: node.next, role: POINTER_ROLES.TRAVERSING },
        ],
        variables:    { current: node.next, index: position + 1 },
        pseudocodeLine: 6,
        isKeyStep:    false,
      }));
    } else {
      steps.push(createStep({
        stepIndex: idx++,
        state,
        action:       ACTIONS.ADVANCE_CURRENT_TO_NULL,
        explanation:  `current ← current.next. The current node (value: ${node.value}) is the tail. current becomes null --, the loop will exit.`,
        nodeHighlights: [{ nodeId: currentId, role: NODE_ROLES.TAIL }],
        variables:    { current: null, index: position + 1 },
        pseudocodeLine: 6,
        isKeyStep:    false,
      }));
    }

    currentId = node.next;
    position += 1;
  }

  // Not found
  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.VALUE_NOT_FOUND,
    explanation:  `current is null --, we have exhausted the list without finding ${target}. Returning −1. The search required ${position} comparison${position !== 1 ? 's' : ''}.`,
    nodeHighlights: [],
    variables:    { current: null, index: position },
    pseudocodeLine: 9,
    isKeyStep:    true,
  }));

  return steps;
}