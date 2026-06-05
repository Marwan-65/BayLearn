/**
 * OPERATION: INSERT
 *
 * Three variants:
 *   insertAtHead  --, O(1), updates head
 *   insertAtTail  --, O(n), must traverse to find the tail
 *   insertAtIndex --, O(n), must traverse to find position
 *
 * A key teaching point: insertAtHead is the only O(1) insert.
 * All others require traversal, which is why arrays are sometimes preferred
 * for random-access inserts.
 */

import { cloneState, createStep, generateId } from './shared.js';
import { NODE_ROLES, POINTER_ROLES, ACTIONS, createNode } from '../schema/index.js';

// ─── Pseudocode ───────────────────────────────────────────────────────────────

export const INSERT_AT_HEAD_PSEUDOCODE = [
  /* 0 */ 'newNode ← createNode(value)',
  /* 1 */ 'newNode.next ← head',
  /* 2 */ 'head ← newNode',
  /* 3 */ 'size ← size + 1',
];

export const INSERT_AT_TAIL_PSEUDOCODE = [
  /* 0 */ 'newNode ← createNode(value)',
  /* 1 */ 'IF head = NULL THEN',
  /* 2 */ '    head ← newNode',
  /* 3 */ '    size ← size + 1',
  /* 4 */ '    RETURN',
  /* 5 */ 'END IF',
  /* 6 */ 'current ← head',
  /* 7 */ 'WHILE current.next ≠ NULL DO',
  /* 8 */ '    current ← current.next',
  /* 9 */ 'END WHILE',
  /* 10 */ 'current.next ← newNode',
  /* 11 */ 'size ← size + 1',
];

export const INSERT_AT_INDEX_PSEUDOCODE = [
  /* 0 */ 'IF index = 0 THEN insertAtHead(value); RETURN',
  /* 1 */ 'IF index > size THEN ERROR "index out of bounds"',
  /* 2 */ 'newNode ← createNode(value)',
  /* 3 */ 'prev ← head',
  /* 4 */ 'i ← 0',
  /* 5 */ 'WHILE i < index − 1 DO',
  /* 6 */ '    prev ← prev.next',
  /* 7 */ '    i ← i + 1',
  /* 8 */ 'END WHILE',
  /* 9 */ 'newNode.next ← prev.next',
  /* 10 */ 'prev.next ← newNode',
  /* 11 */ 'size ← size + 1',
];

// ─── insertAtHead ─────────────────────────────────────────────────────────────

/**
 * Inserts a new node at the front of the list.
 * Time complexity: O(1) --, no traversal needed.
 *
 * @param {ListState} list
 * @param {*}         value
 * @returns {Step[]}
 */
export function insertAtHead(list, value) {
  const steps = [];
  let idx = 0;
  const state = cloneState(list);

  // ── Announce ───────────────────────────────────────────────────────────

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.INITIAL_STATE,
    explanation:  `We are going to insert the value ${value} at the head of the list. Insert-at-head is O(1) --, it takes the same time regardless of list length, because we never need to traverse.`,
    nodeHighlights: state.head ? [{ nodeId: state.head, role: NODE_ROLES.HEAD }] : [],
    variables:    {},
    pseudocodeLine: null,
    isKeyStep:    true,
  }));

  // ── Step 1: Create the new node ────────────────────────────────────────

  const newId = generateId(state);
  state.nodes[newId] = createNode(newId, value, null);
  // Note: not yet linked into the list --, size/head unchanged yet

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.CREATE_NODE,
    explanation:  `We allocate a new node with value ${value}. At this moment it exists in memory but is not yet connected to the list. Its "next" pointer is null.`,
    nodeHighlights: [{ nodeId: newId, role: NODE_ROLES.NEW }],
    variables:    { newNode: newId },
    pseudocodeLine: 0,
    isKeyStep:    true,
  }));

  // ── Step 2: newNode.next ← head ────────────────────────────────────────

  const oldHead = state.head;
  state.nodes[newId].next = oldHead;

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.SET_NEW_NEXT,
    explanation:  oldHead === null
      ? `newNode.next ← head. The list was empty, so head is null. We set newNode.next = null. The new node will become both head and tail.`
      : `newNode.next ← head. We point the new node's "next" at the current head (value: ${list.nodes[oldHead].value}). The new node is now wired to the front of the existing list --, but "head" still points to the old node. ⚠️ Order matters: we must set newNode.next BEFORE updating head, or we would lose the reference to the rest of the list.`,
    nodeHighlights: [
      { nodeId: newId, role: NODE_ROLES.INSERTING },
      ...(oldHead ? [{ nodeId: oldHead, role: NODE_ROLES.HEAD }] : []),
    ],
    pointerHighlights: oldHead ? [
      { fromId: newId, toId: oldHead, role: POINTER_ROLES.NEW },
    ] : [],
    variables:    { newNode: newId },
    pseudocodeLine: 1,
    isKeyStep:    true,
  }));

  // ── Step 3: head ← newNode ─────────────────────────────────────────────

  state.head = newId;
  state.size += 1;

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.UPDATE_HEAD,
    explanation:  `head ← newNode. We update the list's head pointer to reference the new node. The new node is now officially the first node in the list. The old head (${oldHead ? `value: ${list.nodes[oldHead].value}` : 'none'}) is still reachable via newNode.next.`,
    nodeHighlights: [
      { nodeId: newId, role: NODE_ROLES.HEAD },
      ...(oldHead ? [{ nodeId: oldHead, role: NODE_ROLES.VISITING }] : []),
    ],
    variables:    { newNode: newId },
    pseudocodeLine: 2,
    isKeyStep:    true,
  }));

  // ── Step 4: Complete ───────────────────────────────────────────────────

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.OPERATION_COMPLETE,
    explanation:  `Insert complete. The value ${value} is now at the head of the list. The list now has ${state.size} node${state.size !== 1 ? 's' : ''}. This operation took O(1) time --, just 2 pointer updates, regardless of how long the list is.`,
    nodeHighlights: [{ nodeId: newId, role: NODE_ROLES.HEAD }],
    variables:    {},
    pseudocodeLine: 3,
    isKeyStep:    true,
  }));

  return steps;
}

// ─── insertAtTail ─────────────────────────────────────────────────────────────

/**
 * Inserts a new node at the end of the list.
 * Time complexity: O(n) --, must traverse to find the tail.
 *
 * @param {ListState} list
 * @param {*}         value
 * @returns {Step[]}
 */
export function insertAtTail(list, value) {
  const steps = [];
  let idx = 0;
  const state = cloneState(list);

  // ── Announce ───────────────────────────────────────────────────────────

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.INITIAL_STATE,
    explanation:  `We are going to insert the value ${value} at the tail of the list. Unlike insert-at-head, this is O(n) --, we must walk the whole list to find the last node, because a singly linked list has no tail pointer.`,
    nodeHighlights: state.head ? [{ nodeId: state.head, role: NODE_ROLES.HEAD }] : [],
    variables:    {},
    pseudocodeLine: null,
    isKeyStep:    true,
  }));

  // ── Step 1: Create the new node ────────────────────────────────────────

  const newId = generateId(state);
  state.nodes[newId] = createNode(newId, value, null);

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.CREATE_NODE,
    explanation:  `We create a new node with value ${value}. Its "next" is null --, tail nodes always point to null.`,
    nodeHighlights: [{ nodeId: newId, role: NODE_ROLES.NEW }],
    variables:    { newNode: newId },
    pseudocodeLine: 0,
    isKeyStep:    true,
  }));

  // ── Step 2: Handle empty list ──────────────────────────────────────────

  if (state.head === null) {
    state.head = newId;
    state.size += 1;

    steps.push(createStep({
      stepIndex: idx++,
      state,
      action:       ACTIONS.UPDATE_HEAD,
      explanation:  `The list is empty (head = null). A tail insert into an empty list is the same as a head insert --, the new node becomes both the head and the tail.`,
      nodeHighlights: [{ nodeId: newId, role: NODE_ROLES.HEAD }],
      variables:    { newNode: newId },
      pseudocodeLine: 2,
      isKeyStep:    true,
    }));

    steps.push(createStep({
      stepIndex: idx++,
      state,
      action:       ACTIONS.OPERATION_COMPLETE,
      explanation:  `Insert complete. ${value} is now the only node in the list (it is both head and tail).`,
      nodeHighlights: [{ nodeId: newId, role: NODE_ROLES.HEAD }],
      variables:    {},
      pseudocodeLine: 4,
      isKeyStep:    true,
    }));

    return steps;
  }

  // ── Step 3: Traverse to the tail ───────────────────────────────────────

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.SET_CURRENT_TO_HEAD,
    explanation:  `The list is not empty. We need to find the tail. We start a "current" pointer at the head and walk forward until current.next is null.`,
    nodeHighlights: [{ nodeId: state.head, role: NODE_ROLES.VISITING }],
    variables:    { newNode: newId, current: state.head },
    pseudocodeLine: 6,
    isKeyStep:    true,
  }));

  let currentId = list.head;   // use original list to traverse (state.nodes is the same)
  const visited = new Set();

  while (state.nodes[currentId].next !== null) {
    if (visited.has(currentId)) break;
    visited.add(currentId);

    const node = state.nodes[currentId];

    steps.push(createStep({
      stepIndex: idx++,
      state,
      action:       ACTIONS.TRAVERSE_TO_TAIL,
      explanation:  `current.next is not null (it points to value ${state.nodes[node.next].value}), so we have not reached the tail yet. We advance: current ← current.next.`,
      nodeHighlights: [
        { nodeId: currentId,  role: NODE_ROLES.DEFAULT },
        { nodeId: node.next,  role: NODE_ROLES.VISITING },
      ],
      pointerHighlights: [
        { fromId: currentId, toId: node.next, role: POINTER_ROLES.TRAVERSING },
      ],
      variables:    { newNode: newId, current: node.next },
      pseudocodeLine: 8,
      isKeyStep:    false,
    }));

    currentId = node.next;
  }

  // currentId is now the tail
  const tailNode = state.nodes[currentId];

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.CHECK_WHILE_CONDITION,
    explanation:  `current.next is null --, we have found the tail node (value: ${tailNode.value}). The WHILE loop exits.`,
    nodeHighlights: [{ nodeId: currentId, role: NODE_ROLES.TAIL }],
    variables:    { newNode: newId, current: currentId },
    pseudocodeLine: 9,
    isKeyStep:    true,
  }));

  // ── Step 4: Attach the new node ────────────────────────────────────────

  state.nodes[currentId].next = newId;
  state.size += 1;

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.ATTACH_TO_TAIL,
    explanation:  `current.next ← newNode. We update the tail node's "next" pointer to point to our new node. The new node is now the last node in the list.`,
    nodeHighlights: [
      { nodeId: currentId, role: NODE_ROLES.DEFAULT },
      { nodeId: newId,     role: NODE_ROLES.INSERTING },
    ],
    pointerHighlights: [
      { fromId: currentId, toId: newId, role: POINTER_ROLES.NEW },
    ],
    variables:    { newNode: newId, current: currentId },
    pseudocodeLine: 10,
    isKeyStep:    true,
  }));

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.OPERATION_COMPLETE,
    explanation:  `Insert complete. The value ${value} is now the tail of the list. The list now has ${state.size} nodes. This took O(n) time because we had to traverse ${list.size} node${list.size !== 1 ? 's' : ''} to reach the tail.`,
    nodeHighlights: [{ nodeId: newId, role: NODE_ROLES.TAIL }],
    variables:    {},
    pseudocodeLine: 11,
    isKeyStep:    true,
  }));

  return steps;
}

// ─── insertAtIndex ────────────────────────────────────────────────────────────

/**
 * Inserts a new node at a given 0-based index.
 * Index 0 is equivalent to insertAtHead.
 * Index === list.size is equivalent to insertAtTail.
 *
 * Time complexity: O(n).
 *
 * @param {ListState} list
 * @param {*}         value
 * @param {number}    index  0-based
 * @returns {Step[]}
 */
export function insertAtIndex(list, value, index) {
  const steps = [];
  let idx = 0;
  const state = cloneState(list);

  // ── Announce ───────────────────────────────────────────────────────────

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.INITIAL_STATE,
    explanation:  `We are going to insert the value ${value} at index ${index} (0-based). The list currently has ${list.size} node${list.size !== 1 ? 's' : ''}, so valid insertion indices are 0 to ${list.size}.`,
    nodeHighlights: state.head ? [{ nodeId: state.head, role: NODE_ROLES.HEAD }] : [],
    variables:    {},
    pseudocodeLine: null,
    isKeyStep:    true,
  }));

  // ── Guard: index 0 → insertAtHead ──────────────────────────────────────

  if (index === 0) {
    steps.push(createStep({
      stepIndex: idx++,
      state,
      action:       ACTIONS.CHECK_WHILE_CONDITION,
      explanation:  `Index is 0 --, this is a head insert. We delegate to the insertAtHead logic.`,
      nodeHighlights: [],
      variables:    {},
      pseudocodeLine: 0,
      isKeyStep:    true,
    }));
    // Splice in the insertAtHead steps (re-indexed)
    const headSteps = insertAtHead(list, value);
    headSteps.forEach(s => steps.push({ ...s, stepIndex: idx++ }));
    return steps;
  }

  // ── Guard: out-of-bounds ────────────────────────────────────────────────

  if (index > list.size) {
    steps.push(createStep({
      stepIndex: idx++,
      state,
      action:       ACTIONS.INDEX_OUT_OF_BOUNDS,
      explanation:  `❌ Index ${index} is out of bounds. The list only has ${list.size} node${list.size !== 1 ? 's' : ''}, so the maximum valid insertion index is ${list.size}. The operation is aborted.`,
      nodeHighlights: [],
      variables:    {},
      pseudocodeLine: 1,
      isKeyStep:    true,
    }));
    return steps;
  }

  // ── Step 1: Create the new node ────────────────────────────────────────

  const newId = generateId(state);
  state.nodes[newId] = createNode(newId, value, null);

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.CREATE_NODE,
    explanation:  `We create a new node with value ${value}. We need to find the node currently at index ${index - 1} so we can insert after it.`,
    nodeHighlights: [{ nodeId: newId, role: NODE_ROLES.NEW }],
    variables:    { newNode: newId },
    pseudocodeLine: 2,
    isKeyStep:    true,
  }));

  // ── Step 2: Traverse to position (index - 1) ───────────────────────────

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.TRAVERSE_TO_INDEX,
    explanation:  `We set prev ← head and walk forward until we reach index ${index - 1}. "prev" will be the node that should precede the new node.`,
    nodeHighlights: [{ nodeId: state.head, role: NODE_ROLES.VISITING }],
    variables:    { newNode: newId, prev: state.head, i: 0 },
    pseudocodeLine: 3,
    isKeyStep:    true,
  }));

  let prevId = list.head;
  const visited = new Set();

  for (let i = 0; i < index - 1; i++) {
    if (visited.has(prevId)) break;
    visited.add(prevId);

    const prevNode = state.nodes[prevId];
    const nextId = prevNode.next;

    steps.push(createStep({
      stepIndex: idx++,
      state,
      action:       ACTIONS.TRAVERSE_TO_INDEX,
      explanation:  `i = ${i}, which is less than ${index - 1}. We advance: prev ← prev.next (from value ${prevNode.value} to value ${state.nodes[nextId].value}). i becomes ${i + 1}.`,
      nodeHighlights: [
        { nodeId: prevId,  role: NODE_ROLES.DEFAULT },
        { nodeId: nextId,  role: NODE_ROLES.VISITING },
      ],
      pointerHighlights: [
        { fromId: prevId, toId: nextId, role: POINTER_ROLES.TRAVERSING },
      ],
      variables:    { newNode: newId, prev: nextId, i: i + 1 },
      pseudocodeLine: 6,
      isKeyStep:    false,
    }));

    prevId = nextId;
  }

  const prevNode = state.nodes[prevId];
  const afterId  = prevNode.next;   // the node that currently lives at `index`

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.CHECK_WHILE_CONDITION,
    explanation:  `We have reached index ${index - 1} --, the node with value ${prevNode.value}. The node currently at index ${index} is ${afterId ? `value: ${state.nodes[afterId].value}` : 'null (tail insert)'}. Now we wire in the new node.`,
    nodeHighlights: [
      { nodeId: prevId, role: NODE_ROLES.PREV },
      ...(afterId ? [{ nodeId: afterId, role: NODE_ROLES.VISITING }] : []),
    ],
    variables:    { newNode: newId, prev: prevId },
    pseudocodeLine: 8,
    isKeyStep:    true,
  }));

  // ── Step 3: newNode.next ← prev.next ───────────────────────────────────

  state.nodes[newId].next = afterId;

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.SET_NEW_NEXT,
    explanation:  afterId
      ? `newNode.next ← prev.next. We point the new node at the node that was at index ${index} (value: ${state.nodes[afterId].value}). ⚠️ We do this FIRST --, if we updated prev.next first, we would lose this reference.`
      : `newNode.next ← prev.next. prev.next is null (prev is the tail), so newNode.next = null. The new node will become the new tail.`,
    nodeHighlights: [
      { nodeId: newId,  role: NODE_ROLES.INSERTING },
      { nodeId: prevId, role: NODE_ROLES.PREV },
      ...(afterId ? [{ nodeId: afterId, role: NODE_ROLES.VISITING }] : []),
    ],
    pointerHighlights: afterId ? [
      { fromId: newId, toId: afterId, role: POINTER_ROLES.NEW },
    ] : [],
    variables:    { newNode: newId, prev: prevId },
    pseudocodeLine: 9,
    isKeyStep:    true,
  }));

  // ── Step 4: prev.next ← newNode ────────────────────────────────────────

  state.nodes[prevId].next = newId;
  state.size += 1;

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.WIRE_NEW_NODE,
    explanation:  `prev.next ← newNode. We update the previous node's pointer to reference the new node. The new node is now at index ${index} in the list, sitting between "${prevNode.value}" and "${afterId ? state.nodes[afterId].value : 'null'}".`,
    nodeHighlights: [
      { nodeId: prevId, role: NODE_ROLES.DEFAULT },
      { nodeId: newId,  role: NODE_ROLES.INSERTING },
      ...(afterId ? [{ nodeId: afterId, role: NODE_ROLES.DEFAULT }] : []),
    ],
    pointerHighlights: [
      { fromId: prevId, toId: newId, role: POINTER_ROLES.UPDATING },
    ],
    variables:    {},
    pseudocodeLine: 10,
    isKeyStep:    true,
  }));

  steps.push(createStep({
    stepIndex: idx++,
    state,
    action:       ACTIONS.OPERATION_COMPLETE,
    explanation:  `Insert complete. The value ${value} is now at index ${index}. The list has ${state.size} nodes. This took O(n) time because we traversed ${index} node${index !== 1 ? 's' : ''} to reach the insertion point.`,
    nodeHighlights: [{ nodeId: newId, role: NODE_ROLES.INSERTING }],
    variables:    {},
    pseudocodeLine: 11,
    isKeyStep:    true,
  }));

  return steps;
}