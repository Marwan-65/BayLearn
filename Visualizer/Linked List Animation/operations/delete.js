/**
 * OPERATION: DELETE
 *
 * Four variants:
 *   deleteAtHead   --, O(1)
 *   deleteAtTail   --, O(n), must find second-to-last node
 *   deleteByValue  --, O(n), two-pointer technique (prev + current)
 *   deleteAtIndex  --, O(n), two-pointer technique
 *
 * Key teaching points:
 *   - deleteAtHead is O(1) because head is directly accessible
 *   - deleteAtTail is O(n) because we need the node BEFORE the tail, and
 *     singly linked lists can only move forward
 *   - The two-pointer pattern (prev + current) is fundamental to linked list
 *     deletion and will reappear in many other algorithms
 */

import { cloneState, createStep } from './shared.js';
import { NODE_ROLES, POINTER_ROLES, ACTIONS } from '../schema/index.js';

// ─── Pseudocode ───────────────────────────────────────────────────────────────

export const DELETE_AT_HEAD_PSEUDOCODE = [
  /* 0 */ 'IF head = NULL THEN RETURN (empty list)',
  /* 1 */ 'deleted ← head.value',
  /* 2 */ 'head ← head.next',
  /* 3 */ 'size ← size − 1',
  /* 4 */ 'RETURN deleted',
];

export const DELETE_AT_TAIL_PSEUDOCODE = [
  /* 0 */ 'IF head = NULL THEN RETURN (empty list)',
  /* 1 */ 'IF head.next = NULL THEN',
  /* 2 */ '    deleted ← head.value',
  /* 3 */ '    head ← NULL',
  /* 4 */ '    size ← size − 1',
  /* 5 */ '    RETURN deleted',
  /* 6 */ 'END IF',
  /* 7 */ 'prev ← head',
  /* 8 */ 'WHILE prev.next.next ≠ NULL DO',
  /* 9 */ '    prev ← prev.next',
  /* 10 */ 'END WHILE',
  /* 11 */ 'deleted ← prev.next.value',
  /* 12 */ 'prev.next ← NULL',
  /* 13 */ 'size ← size − 1',
  /* 14 */ 'RETURN deleted',
];

export const DELETE_BY_VALUE_PSEUDOCODE = [
  /* 0 */ 'IF head = NULL THEN RETURN false',
  /* 1 */ 'IF head.value = target THEN',
  /* 2 */ '    head ← head.next',
  /* 3 */ '    size ← size − 1',
  /* 4 */ '    RETURN true',
  /* 5 */ 'END IF',
  /* 6 */ 'prev ← head',
  /* 7 */ 'current ← head.next',
  /* 8 */ 'WHILE current ≠ NULL DO',
  /* 9 */ '    IF current.value = target THEN',
  /* 10 */ '        prev.next ← current.next',
  /* 11 */ '        size ← size − 1',
  /* 12 */ '        RETURN true',
  /* 13 */ '    END IF',
  /* 14 */ '    prev ← current',
  /* 15 */ '    current ← current.next',
  /* 16 */ 'END WHILE',
  /* 17 */ 'RETURN false',
];

export const DELETE_AT_INDEX_PSEUDOCODE = [
  /* 0 */ 'IF index < 0 OR index ≥ size THEN ERROR',
  /* 1 */ 'IF index = 0 THEN deleteAtHead(); RETURN',
  /* 2 */ 'prev ← head',
  /* 3 */ 'i ← 0',
  /* 4 */ 'WHILE i < index − 1 DO',
  /* 5 */ '    prev ← prev.next',
  /* 6 */ '    i ← i + 1',
  /* 7 */ 'END WHILE',
  /* 8 */ 'deleted ← prev.next.value',
  /* 9 */ 'prev.next ← prev.next.next',
  /* 10 */ 'size ← size − 1',
  /* 11 */ 'RETURN deleted',
];

// ─── deleteAtHead ─────────────────────────────────────────────────────────────

/**
 * Removes the head node and returns its value.
 * Time complexity: O(1).
 *
 * @param {ListState} list
 * @returns {Step[]}
 */
export function deleteAtHead(list) {
  const steps = [];
  let idx = 0;
  const state = cloneState(list);

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.INITIAL_STATE,
    explanation:  `We are going to delete the head node. This is O(1) --, no traversal needed, because we always have a direct reference to the head.`,
    nodeHighlights: state.head ? [{ nodeId: state.head, role: NODE_ROLES.HEAD }] : [],
    variables:    {},
    pseudocodeLine: null,
    isKeyStep:    true,
  }));

  // Guard: empty list
  if (state.head === null) {
    steps.push(createStep({
      stepIndex: idx++,
      state,
      action:       ACTIONS.LIST_EMPTY,
      explanation:  `The list is empty --, there is no head node to delete. The operation is a no-op.`,
      nodeHighlights: [],
      variables:    {},
      pseudocodeLine: 0,
      isKeyStep:    true,
    }));
    return steps;
  }

  const deletedId    = state.head;
  const deletedValue = state.nodes[deletedId].value;
  const nextId       = state.nodes[deletedId].next;

  // Step: identify the node to delete
  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.IDENTIFY_HEAD_DELETE,
    explanation:  `The head node holds value ${deletedValue}. We will remove it. The new head will be ${nextId ? `the node with value ${state.nodes[nextId].value}` : 'null (the list will become empty)'}.`,
    nodeHighlights: [
      { nodeId: deletedId, role: NODE_ROLES.DELETING },
      ...(nextId ? [{ nodeId: nextId, role: NODE_ROLES.VISITING }] : []),
    ],
    variables:    {},
    pseudocodeLine: 1,
    isKeyStep:    true,
  }));

  // Step: head ← head.next
  delete state.nodes[deletedId];
  state.head = nextId;
  state.size -= 1;

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.ADVANCE_HEAD,
    explanation:  `head ← head.next. We move the head pointer to the next node. The old head node (value: ${deletedValue}) is no longer referenced by anything and will be garbage collected.`,
    nodeHighlights: nextId ? [{ nodeId: nextId, role: NODE_ROLES.HEAD }] : [],
    variables:    {},
    pseudocodeLine: 2,
    isKeyStep:    true,
  }));

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.OPERATION_COMPLETE,
    explanation:  `Delete complete. The value ${deletedValue} has been removed. The list now has ${state.size} node${state.size !== 1 ? 's' : ''}.`,
    nodeHighlights: nextId ? [{ nodeId: nextId, role: NODE_ROLES.HEAD }] : [],
    variables:    {},
    pseudocodeLine: 4,
    isKeyStep:    true,
  }));

  return steps;
}

// ─── deleteAtTail ─────────────────────────────────────────────────────────────

/**
 * Removes the tail node and returns its value.
 * Time complexity: O(n) --, must find the second-to-last node.
 *
 * @param {ListState} list
 * @returns {Step[]}
 */
export function deleteAtTail(list) {
  const steps = [];
  let idx = 0;
  const state = cloneState(list);

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.INITIAL_STATE,
    explanation:  `We are going to delete the tail node. This is O(n) --, even though we want the last node, we need the second-to-last node to update its "next" pointer to null. There is no way to go backwards in a singly linked list.`,
    nodeHighlights: state.head ? [{ nodeId: state.head, role: NODE_ROLES.HEAD }] : [],
    variables:    {},
    pseudocodeLine: null,
    isKeyStep:    true,
  }));

  // Guard: empty list
  if (state.head === null) {
    steps.push(createStep({
      stepIndex: idx++,
      state,
      action:       ACTIONS.LIST_EMPTY,
      explanation:  `The list is empty. Nothing to delete.`,
      nodeHighlights: [],
      variables:    {},
      pseudocodeLine: 0,
      isKeyStep:    true,
    }));
    return steps;
  }

  // Guard: single node
  if (state.nodes[state.head].next === null) {
    const onlyId    = state.head;
    const onlyValue = state.nodes[onlyId].value;

    steps.push(createStep({
      stepIndex: idx++,
      state,
      action:       ACTIONS.IDENTIFY_HEAD_DELETE,
      explanation:  `There is only one node in the list (value: ${onlyValue}). It is both head and tail. Deleting it will leave the list empty.`,
      nodeHighlights: [{ nodeId: onlyId, role: NODE_ROLES.DELETING }],
      variables:    {},
      pseudocodeLine: 1,
      isKeyStep:    true,
    }));

    delete state.nodes[onlyId];
    state.head = null;
    state.size  = 0;

    steps.push(createStep({
      stepIndex: idx++,
      state,
      action:       ACTIONS.OPERATION_COMPLETE,
      explanation:  `head ← null. The list is now empty.`,
      nodeHighlights: [],
      variables:    {},
      pseudocodeLine: 3,
      isKeyStep:    true,
    }));

    return steps;
  }

  // Traverse to find the second-to-last node
  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.TRAVERSE_TO_PREV,
    explanation:  `We need to find the second-to-last node so we can set its "next" to null. We start "prev" at the head and walk forward while prev.next.next ≠ null.`,
    nodeHighlights: [{ nodeId: state.head, role: NODE_ROLES.VISITING }],
    variables:    { prev: state.head },
    pseudocodeLine: 7,
    isKeyStep:    true,
  }));

  let prevId = list.head;
  const visited = new Set();

  while (state.nodes[prevId].next !== null &&
         state.nodes[state.nodes[prevId].next].next !== null) {
    if (visited.has(prevId)) break;
    visited.add(prevId);

    const nextId = state.nodes[prevId].next;

    steps.push(createStep({
      stepIndex: idx++,
      state,
      action:       ACTIONS.TRAVERSE_TO_PREV,
      explanation:  `prev.next.next is not null, so we have not yet found the second-to-last node. We advance: prev ← prev.next.`,
      nodeHighlights: [
        { nodeId: prevId,  role: NODE_ROLES.DEFAULT },
        { nodeId: nextId,  role: NODE_ROLES.VISITING },
      ],
      pointerHighlights: [
        { fromId: prevId, toId: nextId, role: POINTER_ROLES.TRAVERSING },
      ],
      variables:    { prev: nextId },
      pseudocodeLine: 9,
      isKeyStep:    false,
    }));

    prevId = nextId;
  }

  const tailId    = state.nodes[prevId].next;
  const tailValue = state.nodes[tailId].value;

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.IDENTIFY_TARGET,
    explanation:  `We found the second-to-last node (value: ${state.nodes[prevId].value}). Its next is the tail (value: ${tailValue}), which is what we will delete. We set prev.next ← null.`,
    nodeHighlights: [
      { nodeId: prevId, role: NODE_ROLES.PREV },
      { nodeId: tailId, role: NODE_ROLES.DELETING },
    ],
    variables:    { prev: prevId },
    pseudocodeLine: 11,
    isKeyStep:    true,
  }));

  // Perform the deletion
  delete state.nodes[tailId];
  state.nodes[prevId].next = null;
  state.size -= 1;

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.OPERATION_COMPLETE,
    explanation:  `prev.next ← null. The tail node (value: ${tailValue}) has been removed. The node with value ${state.nodes[prevId].value} is now the new tail. The list has ${state.size} node${state.size !== 1 ? 's' : ''}.`,
    nodeHighlights: [{ nodeId: prevId, role: NODE_ROLES.TAIL }],
    variables:    {},
    pseudocodeLine: 14,
    isKeyStep:    true,
  }));

  return steps;
}

// ─── deleteByValue ────────────────────────────────────────────────────────────

/**
 * Removes the first node whose value equals `target`.
 * Time complexity: O(n).
 *
 * @param {ListState} list
 * @param {*}         target
 * @returns {Step[]}
 */
export function deleteByValue(list, target) {
  const steps = [];
  let idx = 0;
  const state = cloneState(list);

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.INITIAL_STATE,
    explanation:  `We are going to delete the first node with value ${target}. We will use two pointers --, "prev" and "current" --, so that when we find the target we can immediately update prev.next to skip over it.`,
    nodeHighlights: state.head ? [{ nodeId: state.head, role: NODE_ROLES.HEAD }] : [],
    variables:    {},
    pseudocodeLine: null,
    isKeyStep:    true,
  }));

  // Guard: empty list
  if (state.head === null) {
    steps.push(createStep({
      stepIndex: idx++,
      state,
      action:       ACTIONS.LIST_EMPTY,
      explanation:  `The list is empty. Nothing to delete.`,
      nodeHighlights: [],
      variables:    {},
      pseudocodeLine: 0,
      isKeyStep:    true,
    }));
    return steps;
  }

  // Check head first
  const headNode = state.nodes[state.head];

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.COMPARE_VALUE,
    explanation:  `We check the head node first: is ${headNode.value} === ${target}? ${headNode.value === target ? 'Yes! We can delete immediately without a two-pointer traversal.' : 'No. We need to traverse further.'}`,
    nodeHighlights: [{ nodeId: state.head, role: NODE_ROLES.COMPARING }],
    variables:    {},
    pseudocodeLine: 1,
    isKeyStep:    true,
  }));

  if (headNode.value === target) {
    const deletedId = state.head;
    const nextId    = headNode.next;
    delete state.nodes[deletedId];
    state.head = nextId;
    state.size -= 1;

    steps.push(createStep({
      stepIndex: idx++,
      state,
      action:       ACTIONS.ADVANCE_HEAD,
      explanation:  `head ← head.next. The head was our target. We simply advance the head pointer, and the old head node is removed.`,
      nodeHighlights: nextId ? [{ nodeId: nextId, role: NODE_ROLES.HEAD }] : [],
      variables:    {},
      pseudocodeLine: 2,
      isKeyStep:    true,
    }));

    steps.push(createStep({
      stepIndex: idx++,
      state,
      action:       ACTIONS.OPERATION_COMPLETE,
      explanation:  `Delete complete. The node with value ${target} has been removed from the head. The list now has ${state.size} node${state.size !== 1 ? 's' : ''}.`,
      nodeHighlights: [],
      variables:    {},
      pseudocodeLine: 4,
      isKeyStep:    true,
    }));

    return steps;
  }

  // Two-pointer traversal
  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.TRAVERSE_TO_PREV,
    explanation:  `The head is not our target. We set prev ← head and current ← head.next and start a two-pointer traversal. "prev" always stays one step behind "current".`,
    nodeHighlights: [
      { nodeId: state.head,                    role: NODE_ROLES.PREV },
      ...(headNode.next ? [{ nodeId: headNode.next, role: NODE_ROLES.VISITING }] : []),
    ],
    variables:    { prev: state.head, current: headNode.next },
    pseudocodeLine: 6,
    isKeyStep:    true,
  }));

  let prevId    = list.head;
  let currentId = list.nodes[list.head].next;
  const visited = new Set();

  while (currentId !== null) {
    if (visited.has(currentId)) break;
    visited.add(currentId);

    const currentNode = state.nodes[currentId];

    steps.push(createStep({
      stepIndex: idx++,
      state,
      action:       ACTIONS.COMPARE_VALUE,
      explanation:  `Is current.value (${currentNode.value}) === ${target}? ${currentNode.value === target ? 'Yes --, found the target!' : 'No --, keep searching.'}`,
      nodeHighlights: [
        { nodeId: prevId,    role: NODE_ROLES.PREV },
        { nodeId: currentId, role: NODE_ROLES.COMPARING },
      ],
      variables:    { prev: prevId, current: currentId },
      pseudocodeLine: 9,
      isKeyStep:    currentNode.value === target,
    }));

    if (currentNode.value === target) {
      // Found --, bypass the current node
      const nextId = currentNode.next;
      delete state.nodes[currentId];
      state.nodes[prevId].next = nextId;
      state.size -= 1;

      steps.push(createStep({
        stepIndex: idx++,
        state,
        action:       ACTIONS.BYPASS_NODE,
        explanation:  `prev.next ← current.next. We "bypass" the target node by making the previous node point directly to the node after the target (${nextId ? `value: ${state.nodes[nextId].value}` : 'null'}). The target node (value: ${target}) is now unreachable and will be garbage collected.`,
        nodeHighlights: [
          { nodeId: prevId, role: NODE_ROLES.DEFAULT },
          ...(nextId ? [{ nodeId: nextId, role: NODE_ROLES.VISITING }] : []),
        ],
        pointerHighlights: nextId ? [
          { fromId: prevId, toId: nextId, role: POINTER_ROLES.UPDATING },
        ] : [],
        variables:    {},
        pseudocodeLine: 10,
        isKeyStep:    true,
      }));

      steps.push(createStep({
        stepIndex: idx++,
        state,
        action:       ACTIONS.OPERATION_COMPLETE,
        explanation:  `Delete complete. The first node with value ${target} has been removed. The list has ${state.size} node${state.size !== 1 ? 's' : ''}.`,
        nodeHighlights: [],
        variables:    {},
        pseudocodeLine: 12,
        isKeyStep:    true,
      }));

      return steps;
    }

    // Advance pointers
    steps.push(createStep({
      stepIndex: idx++,
      state,
      action:       ACTIONS.ADVANCE_CURRENT,
      explanation:  `Not a match. We advance both pointers: prev ← current, current ← current.next.`,
      nodeHighlights: [
        { nodeId: currentId, role: NODE_ROLES.PREV },
        ...(currentNode.next ? [{ nodeId: currentNode.next, role: NODE_ROLES.VISITING }] : []),
      ],
      variables:    { prev: currentId, current: currentNode.next },
      pseudocodeLine: 14,
      isKeyStep:    false,
    }));

    prevId    = currentId;
    currentId = currentNode.next;
  }

  // Not found
  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.VALUE_NOT_FOUND,
    explanation:  `current is now null --, we have reached the end of the list without finding the value ${target}. No node was deleted. The list is unchanged.`,
    nodeHighlights: [],
    variables:    { prev: prevId, current: null },
    pseudocodeLine: 17,
    isKeyStep:    true,
  }));

  return steps;
}

// ─── deleteAtIndex ────────────────────────────────────────────────────────────

/**
 * Removes the node at a given 0-based index.
 * Time complexity: O(n).
 *
 * @param {ListState} list
 * @param {number}    index
 * @returns {Step[]}
 */
export function deleteAtIndex(list, index) {
  const steps = [];
  let idx = 0;
  const state = cloneState(list);

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.INITIAL_STATE,
    explanation:  `We are going to delete the node at index ${index} (0-based). The list has ${list.size} node${list.size !== 1 ? 's' : ''}, so valid indices are 0 to ${list.size - 1}.`,
    nodeHighlights: state.head ? [{ nodeId: state.head, role: NODE_ROLES.HEAD }] : [],
    variables:    {},
    pseudocodeLine: null,
    isKeyStep:    true,
  }));

  // Guard: out of bounds
  if (index < 0 || index >= list.size) {
    steps.push(createStep({
      stepIndex: idx++,
      state,
      action:       ACTIONS.INDEX_OUT_OF_BOUNDS,
      explanation:  `❌ Index ${index} is out of bounds. Valid indices are 0 to ${list.size - 1}. The operation is aborted.`,
      nodeHighlights: [],
      variables:    {},
      pseudocodeLine: 0,
      isKeyStep:    true,
    }));
    return steps;
  }

  // Index 0 → deleteAtHead
  if (index === 0) {
    steps.push(createStep({
      stepIndex: idx++,
      state,
      action:       ACTIONS.CHECK_WHILE_CONDITION,
      explanation:  `Index is 0 --, this is a head deletion. Delegating to deleteAtHead.`,
      nodeHighlights: [],
      variables:    {},
      pseudocodeLine: 1,
      isKeyStep:    true,
    }));
    const headSteps = deleteAtHead(list);
    headSteps.forEach(s => steps.push({ ...s, stepIndex: idx++ }));
    return steps;
  }

  // Traverse to index - 1
  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.TRAVERSE_TO_INDEX,
    explanation:  `We need to find the node just BEFORE index ${index} (i.e., the node at index ${index - 1}), so we can re-link around the target.`,
    nodeHighlights: [{ nodeId: state.head, role: NODE_ROLES.VISITING }],
    variables:    { prev: state.head, i: 0 },
    pseudocodeLine: 2,
    isKeyStep:    true,
  }));

  let prevId = list.head;
  const visited = new Set();

  for (let i = 0; i < index - 1; i++) {
    if (visited.has(prevId)) break;
    visited.add(prevId);

    const nextId = state.nodes[prevId].next;

    steps.push(createStep({
      stepIndex: idx++,
      state,
      action:       ACTIONS.TRAVERSE_TO_INDEX,
      explanation:  `i = ${i} < ${index - 1}. Advancing prev forward. (value: ${state.nodes[prevId].value} → ${state.nodes[nextId].value})`,
      nodeHighlights: [
        { nodeId: prevId,  role: NODE_ROLES.DEFAULT },
        { nodeId: nextId,  role: NODE_ROLES.VISITING },
      ],
      variables:    { prev: nextId, i: i + 1 },
      pseudocodeLine: 5,
      isKeyStep:    false,
    }));

    prevId = nextId;
  }

  const targetId    = state.nodes[prevId].next;
  const targetValue = state.nodes[targetId].value;
  const afterId     = state.nodes[targetId].next;

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.IDENTIFY_TARGET,
    explanation:  `We are at index ${index - 1} (value: ${state.nodes[prevId].value}). The node to delete is at index ${index} (value: ${targetValue}).`,
    nodeHighlights: [
      { nodeId: prevId,    role: NODE_ROLES.PREV },
      { nodeId: targetId,  role: NODE_ROLES.DELETING },
      ...(afterId ? [{ nodeId: afterId, role: NODE_ROLES.VISITING }] : []),
    ],
    variables:    { prev: prevId },
    pseudocodeLine: 8,
    isKeyStep:    true,
  }));

  // Delete
  delete state.nodes[targetId];
  state.nodes[prevId].next = afterId;
  state.size -= 1;

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.OPERATION_COMPLETE,
    explanation:  `prev.next ← prev.next.next. We skip over the target node (value: ${targetValue}), linking directly to ${afterId ? `value: ${state.nodes[afterId].value}` : 'null'}. The list now has ${state.size} node${state.size !== 1 ? 's' : ''}.`,
    nodeHighlights: [
      { nodeId: prevId, role: NODE_ROLES.DEFAULT },
      ...(afterId ? [{ nodeId: afterId, role: NODE_ROLES.DEFAULT }] : []),
    ],
    pointerHighlights: afterId ? [
      { fromId: prevId, toId: afterId, role: POINTER_ROLES.UPDATING },
    ] : [],
    variables:    {},
    pseudocodeLine: 11,
    isKeyStep:    true,
  }));

  return steps;
}