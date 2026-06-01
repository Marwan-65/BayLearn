/**
 * NARRATIVE / CONSTANTS
 *
 * Shared data for the narrative layer.
 * Imported by NarrativeLayer, PseudocodePanel, and ComplexityPanel.
 */

// ─── Pseudocode strings per operation ────────────────────────────────────────
// Each array index matches the pseudocodeLine field in a Step.

export const PSEUDOCODES = {
  traverse: [
    'current ← head',
    'WHILE current ≠ NULL DO',
    '    visit(current.value)',
    '    current ← current.next',
    'END WHILE',
  ],
  insertAtHead: [
    'newNode ← createNode(value)',
    'newNode.next ← head',
    'head ← newNode',
    'size ← size + 1',
  ],
  insertAtTail: [
    'newNode ← createNode(value)',
    'IF head = NULL THEN head ← newNode; RETURN',
    'current ← head',
    'WHILE current.next ≠ NULL DO',
    '    current ← current.next',
    'END WHILE',
    'current.next ← newNode',
    'size ← size + 1',
  ],
  insertAtIndex: [
    'IF index = 0 THEN insertAtHead(value); RETURN',
    'IF index > size THEN ERROR "out of bounds"',
    'newNode ← createNode(value)',
    'prev ← head;  i ← 0',
    'WHILE i < index − 1 DO',
    '    prev ← prev.next;  i ← i + 1',
    'END WHILE',
    'newNode.next ← prev.next',
    'prev.next ← newNode',
    'size ← size + 1',
  ],
  deleteAtHead: [
    'IF head = NULL THEN RETURN',
    'deleted ← head.value',
    'head ← head.next',
    'size ← size − 1',
    'RETURN deleted',
  ],
  deleteAtTail: [
    'IF head = NULL THEN RETURN',
    'IF head.next = NULL THEN head ← NULL; RETURN',
    'prev ← head',
    'WHILE prev.next.next ≠ NULL DO',
    '    prev ← prev.next',
    'END WHILE',
    'prev.next ← NULL',
    'size ← size − 1',
  ],
  deleteByValue: [
    'IF head = NULL THEN RETURN false',
    'IF head.value = target THEN head ← head.next; RETURN true',
    'prev ← head;  current ← head.next',
    'WHILE current ≠ NULL DO',
    '    IF current.value = target THEN',
    '        prev.next ← current.next;  RETURN true',
    '    prev ← current;  current ← current.next',
    'END WHILE',
    'RETURN false',
  ],
  deleteAtIndex: [
    'IF index < 0 OR index ≥ size THEN ERROR',
    'IF index = 0 THEN deleteAtHead(); RETURN',
    'prev ← head;  i ← 0',
    'WHILE i < index − 1 DO',
    '    prev ← prev.next;  i ← i + 1',
    'END WHILE',
    'prev.next ← prev.next.next',
    'size ← size − 1',
  ],
  searchByValue: [
    'current ← head;  index ← 0',
    'WHILE current ≠ NULL DO',
    '    IF current.value = target THEN RETURN index',
    '    current ← current.next;  index ← index + 1',
    'END WHILE',
    'RETURN −1',
  ],
  reverse: [
    'prev    ← NULL',
    'current ← head',
    'WHILE current ≠ NULL DO',
    '    next         ← current.next',
    '    current.next ← prev',
    '    prev         ← current',
    '    current      ← next',
    'END WHILE',
    'head ← prev',
  ],
};

// ─── Complexity info per operation ───────────────────────────────────────────

export const COMPLEXITY_MAP = {
  traverse: {
    time: 'O(n)', space: 'O(1)',
    note: 'Every node is visited exactly once. No extra memory needed.',
  },
  insertAtHead: {
    time: 'O(1)', space: 'O(1)',
    note: 'Head is directly accessible --, two pointer updates, no traversal.',
  },
  insertAtTail: {
    time: 'O(n)', space: 'O(1)',
    note: 'No tail pointer exists, so we must walk the whole list first.',
  },
  insertAtIndex: {
    time: 'O(n)', space: 'O(1)',
    note: 'Must traverse to the insertion point. O(1) if index = 0.',
  },
  deleteAtHead: {
    time: 'O(1)', space: 'O(1)',
    note: 'Head is directly accessible --, one pointer update, no traversal.',
  },
  deleteAtTail: {
    time: 'O(n)', space: 'O(1)',
    note: 'Need the second-to-last node to nullify its next --, requires a full walk.',
  },
  deleteByValue: {
    time: 'O(n)', space: 'O(1)',
    note: 'Linear scan with two pointers. Worst case: value at tail or not present.',
  },
  deleteAtIndex: {
    time: 'O(n)', space: 'O(1)',
    note: 'Must traverse to index − 1. O(1) if index = 0.',
  },
  searchByValue: {
    time: 'O(n)', space: 'O(1)',
    note: 'No random access, no sorted order --, every node must be checked.',
  },
  reverse: {
    time: 'O(n)', space: 'O(1)',
    note: 'Single pass with three pointer variables. No copy of the list needed.',
  },
};

// ─── Variable name → colour role mapping ─────────────────────────────────────
// Used by VariableInspector to colour chips consistently.

export const VAR_ROLES = {
  current: 'amber',
  cur:     'amber',
  prev:    'purple',
  newNode: 'green',
  next:    'blue',
  index:   'dim',
  i:       'dim',
};