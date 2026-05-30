/**
 * OPERATION: REVERSE
 *
 * Reverses the linked list in-place using three pointers: prev, current, next.
 *
 * Time complexity:  O(n) --, single pass
 * Space complexity: O(1) --, no extra data structures
 *
 * This is one of the most instructive linked list operations because:
 *   1. It uses THREE simultaneous pointers (prev, current, next)
 *   2. The order of pointer updates matters critically
 *   3. Students often struggle to visualise how the list "rebuilds itself"
 *      in reverse without a second copy
 *
 * Each step is annotated with rich explanations to address common confusion.
 */

import { cloneState, createStep } from './shared.js';
import { NODE_ROLES, POINTER_ROLES, ACTIONS } from '../schema/index.js';

// ─── Pseudocode ───────────────────────────────────────────────────────────────

export const PSEUDOCODE = [
  /* 0 */ 'prev    ← NULL',
  /* 1 */ 'current ← head',
  /* 2 */ 'WHILE current ≠ NULL DO',
  /* 3 */ '    next         ← current.next   (save before overwriting)',
  /* 4 */ '    current.next ← prev           (reverse the pointer)',
  /* 5 */ '    prev         ← current        (advance prev)',
  /* 6 */ '    current      ← next           (advance current)',
  /* 7 */ 'END WHILE',
  /* 8 */ 'head ← prev',
];

// ─── Operation ───────────────────────────────────────────────────────────────

/**
 * Produces the full sequence of steps for reversing a linked list in-place.
 *
 * @param {ListState} list
 * @returns {Step[]}
 */
export function reverse(list) {
  const steps = [];
  let idx = 0;
  const state = cloneState(list);

  // ── Announce ───────────────────────────────────────────────────────────

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.INITIAL_STATE,
    explanation:  `We are going to reverse the list in-place. This means we flip every "next" pointer so that each node points to its previous neighbour instead of its next one. We will use three pointers (prev, current, next) and do this in a single O(n) pass --, no extra list needed.`,
    nodeHighlights: state.head ? [{ nodeId: state.head, role: NODE_ROLES.HEAD }] : [],
    variables:    {},
    pseudocodeLine: null,
    isKeyStep:    true,
  }));

  // Guard: empty or single-node list
  if (state.head === null) {
    steps.push(createStep({
      stepIndex: idx++,
      state,
      action:       ACTIONS.OPERATION_COMPLETE,
      explanation:  `The list is empty. Nothing to reverse.`,
      nodeHighlights: [],
      variables:    {},
      pseudocodeLine: null,
      isKeyStep:    true,
    }));
    return steps;
  }

  if (state.nodes[state.head].next === null) {
    steps.push(createStep({
      stepIndex: idx++,
      state,
      action:       ACTIONS.OPERATION_COMPLETE,
      explanation:  `The list has only one node. A single-node list is already its own reverse.`,
      nodeHighlights: [{ nodeId: state.head, role: NODE_ROLES.HEAD }],
      variables:    {},
      pseudocodeLine: null,
      isKeyStep:    true,
    }));
    return steps;
  }

  // ── Initialise pointers ────────────────────────────────────────────────

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.INIT_POINTERS,
    explanation:  `We initialise three pointers:\n• prev = null (there is nothing before the head yet)\n• current = head (we start processing from the head)\n• next will be set at the start of each iteration to save current.next before we overwrite it`,
    nodeHighlights: [{ nodeId: state.head, role: NODE_ROLES.VISITING }],
    variables:    { prev: null, current: state.head },
    pseudocodeLine: 0,
    isKeyStep:    true,
  }));

  let prevId    = null;
  let currentId = list.head;
  const visited = new Set();

  // ── Main loop ──────────────────────────────────────────────────────────

  while (currentId !== null) {
    if (visited.has(currentId)) break;
    visited.add(currentId);

    const node   = state.nodes[currentId];
    const nextId = node.next;   // save BEFORE we overwrite

    // WHILE condition (passes)
    steps.push(createStep({
      stepIndex: idx++,
      state,
      action:       ACTIONS.CHECK_WHILE_CONDITION,
      explanation:  `Loop condition: is current null? No --, current points to the node with value ${node.value}. We enter the loop.`,
      nodeHighlights: [
        { nodeId: currentId, role: NODE_ROLES.VISITING },
        ...(prevId ? [{ nodeId: prevId, role: NODE_ROLES.PREV }] : []),
      ],
      variables:    { prev: prevId, current: currentId, next: null },
      pseudocodeLine: 2,
      isKeyStep:    false,
    }));

    // Step A: next ← current.next  (save before overwriting)
    steps.push(createStep({
      stepIndex: idx++,
      state,
      action:       ACTIONS.SAVE_NEXT,
      explanation:  `next ← current.next. We MUST save the next node (${nextId ? `value: ${state.nodes[nextId].value}` : 'null'}) before overwriting current.next in the next step. If we skip this, we lose our only reference to the rest of the list --, it becomes unreachable. This is the most common bug students introduce.`,
      nodeHighlights: [
        { nodeId: currentId, role: NODE_ROLES.VISITING },
        ...(nextId ? [{ nodeId: nextId, role: NODE_ROLES.COMPARING }] : []),
        ...(prevId ? [{ nodeId: prevId, role: NODE_ROLES.PREV }] : []),
      ],
      pointerHighlights: nextId ? [
        { fromId: currentId, toId: nextId, role: POINTER_ROLES.TRAVERSING },
      ] : [],
      variables:    { prev: prevId, current: currentId, next: nextId },
      pseudocodeLine: 3,
      isKeyStep:    true,
    }));

    // Step B: current.next ← prev  (reverse the pointer)
    // Mutate the working state
    state.nodes[currentId].next = prevId;

    steps.push(createStep({
      stepIndex: idx++,
      state,
      action:       ACTIONS.REVERSE_POINTER,
      explanation:  `current.next ← prev. We flip the pointer: instead of pointing forward to ${nextId ? `value ${list.nodes[nextId].value}` : 'null'}, this node now points BACKWARD to ${prevId ? `value ${list.nodes[prevId].value}` : 'null (this node will become the new tail)'}. This is the heart of the reversal.`,
      nodeHighlights: [
        { nodeId: currentId, role: NODE_ROLES.INSERTING },
        ...(prevId ? [{ nodeId: prevId, role: NODE_ROLES.PREV }] : []),
      ],
      pointerHighlights: prevId ? [
        { fromId: currentId, toId: prevId, role: POINTER_ROLES.NEW },
      ] : [],
      variables:    { prev: prevId, current: currentId, next: nextId },
      pseudocodeLine: 4,
      isKeyStep:    true,
    }));

    // Step C: prev ← current (advance prev)
    steps.push(createStep({
      stepIndex: idx++,
      state,
      action:       ACTIONS.ADVANCE_POINTERS,
      explanation:  `prev ← current. We slide "prev" forward to the current node. In the next iteration, this node will play the role of "the already-reversed part".`,
      nodeHighlights: [
        { nodeId: currentId, role: NODE_ROLES.PREV },
        ...(nextId ? [{ nodeId: nextId, role: NODE_ROLES.VISITING }] : []),
      ],
      variables:    { prev: currentId, current: currentId, next: nextId },
      pseudocodeLine: 5,
      isKeyStep:    false,
    }));

    // Step D: current ← next (advance current)
    steps.push(createStep({
      stepIndex: idx++,
      state,
      action:       ACTIONS.ADVANCE_POINTERS,
      explanation:  nextId
        ? `current ← next. We advance to the next unprocessed node (value: ${state.nodes[nextId].value}). We still have a reference to it because we saved it earlier.`
        : `current ← next. next was null, so current becomes null. The WHILE loop will exit after this.`,
      nodeHighlights: [
        { nodeId: currentId, role: NODE_ROLES.DEFAULT },
        ...(nextId ? [{ nodeId: nextId, role: NODE_ROLES.VISITING }] : []),
      ],
      variables:    { prev: currentId, current: nextId, next: null },
      pseudocodeLine: 6,
      isKeyStep:    false,
    }));

    prevId    = currentId;
    currentId = nextId;
  }

  // ── Loop exit: current is null ─────────────────────────────────────────

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.CHECK_WHILE_CONDITION,
    explanation:  `current is null --, all pointers have been reversed. "prev" currently points to what was the last node of the original list, which is now the new head.`,
    nodeHighlights: prevId ? [{ nodeId: prevId, role: NODE_ROLES.VISITING }] : [],
    variables:    { prev: prevId, current: null },
    pseudocodeLine: 7,
    isKeyStep:    true,
  }));

  // ── Update head ────────────────────────────────────────────────────────

  const oldHead = state.head;
  state.head    = prevId;

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.UPDATE_HEAD_TO_PREV,
    explanation:  `head ← prev. We update the list's head pointer to "prev", which is the node that was previously the tail. The list is now fully reversed.`,
    nodeHighlights: [{ nodeId: prevId, role: NODE_ROLES.HEAD }],
    variables:    { prev: prevId, current: null },
    pseudocodeLine: 8,
    isKeyStep:    true,
  }));

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.OPERATION_COMPLETE,
    explanation:  `Reversal complete. Every "next" pointer in the list has been flipped. The original head (value: ${list.nodes[oldHead].value}) is now the tail (its next is null). The operation was O(n) time and O(1) space.`,
    nodeHighlights: [{ nodeId: prevId, role: NODE_ROLES.HEAD }],
    variables:    {},
    pseudocodeLine: null,
    isKeyStep:    true,
  }));

  return steps;
}