
export function createNode(id, value, next = null) {
  return { id, value, next };
}


export function createList() {
  return {
    nodes: {},   // { [id: string]: Node }  --, all nodes keyed by ID
    head: null,  // string | null            --, ID of the head node
    size: 0,     //  number                  --, number of nodes
    _nextId: 1,  // number (internal)        --, counter for ID generation
  };
}


export function fromArray(values) {
  if (!Array.isArray(values) || values.length === 0) return createList();

  const list = createList();
  const ids = values.map((_, i) => `n${i + 1}`);

  values.forEach((value, i) => {
    list.nodes[ids[i]] = createNode(ids[i], value, ids[i + 1] ?? null);
  });

  list.head = ids[0];
  list.size = values.length;
  list._nextId = values.length + 1;

  return list;
}


export function getOrderedIds(list) {
  if (list._orderedIds) {
    return list._orderedIds;
  }

  const ids = [];
  let current = list.head;
  const visited = new Set();

  while (current !== null) {
    if (visited.has(current)) break;
    visited.add(current);
    ids.push(current);
    current = list.nodes[current]?.next ?? null;
  }

  return ids;
}


export function toArray(list) {
  return getOrderedIds(list).map(id => list.nodes[id].value);
}


export function getTailId(list) {
  const ids = getOrderedIds(list);
  return ids.length > 0 ? ids[ids.length - 1] : null;
}


export function getNodeAtIndex(list, index) {
  if (index < 0) return null;
  const ids = getOrderedIds(list);
  const id = ids[index] ?? null;
  return id ? list.nodes[id] : null;
}


export function indexOfValue(list, value) {
  const ids = getOrderedIds(list);
  return ids.findIndex(id => list.nodes[id].value === value);
}


export function validateList(list) {
  const errors = [];

  if (!list || typeof list !== 'object') {
    return { valid: false, errors: ['List must be a plain object'] };
  }

  if (list.head !== null && !list.nodes[list.head]) {
    errors.push(`head "${list.head}" does not exist in nodes`);
  }

  Object.entries(list.nodes).forEach(([id, node]) => {
    if (node.id !== id) {
      errors.push(`Node "${id}" has a mismatched .id field ("${node.id}")`);
    }
    if (node.next !== null && !list.nodes[node.next]) {
      errors.push(`Node "${id}" has next → "${node.next}" which does not exist`);
    }
  });

  const actualSize = getOrderedIds(list).length;
  if (actualSize !== list.size) {
    errors.push(`list.size is ${list.size} but traversal found ${actualSize} nodes`);
  }

  return { valid: errors.length === 0, errors };
}

export const NODE_ROLES = Object.freeze({
  DEFAULT:   'default',   // neutral, no special meaning
  HEAD:      'head',      // the head node
  TAIL:      'tail',      // the tail node
  VISITING:  'visiting',  // currently being traversed / "current pointer is here"
  COMPARING: 'comparing', // being tested against a target value
  INSERTING: 'inserting', // newly created, being wired in
  DELETING:  'deleting',  // about to be removed
  FOUND:     'found',     // search target was found here
  NOT_FOUND: 'not_found', // search ended without finding target
  PREV:      'prev',      // the "prev" pointer in a two-pointer traversal
  NEW:       'new',       // freshly created, not yet linked
});

export const POINTER_ROLES = Object.freeze({
  DEFAULT:    'default',    // normal next-pointer
  TRAVERSING: 'traversing', // pointer being actively followed
  UPDATING:   'updating',   // pointer is about to be changed
  NEW:        'new',        // newly created pointer
  BREAKING:   'breaking',   // pointer being severed/nulled
});


export const ACTIONS = Object.freeze({
  // General
  INITIAL_STATE:          'INITIAL_STATE',
  OPERATION_COMPLETE:     'OPERATION_COMPLETE',
  LIST_EMPTY:             'LIST_EMPTY',

  // Traversal
  SET_CURRENT_TO_HEAD:    'SET_CURRENT_TO_HEAD',
  CHECK_WHILE_CONDITION:  'CHECK_WHILE_CONDITION',
  VISIT_NODE:             'VISIT_NODE',
  ADVANCE_CURRENT:        'ADVANCE_CURRENT',
  ADVANCE_CURRENT_TO_NULL:'ADVANCE_CURRENT_TO_NULL',

  // Insert
  CREATE_NODE:            'CREATE_NODE',
  SET_NEW_NEXT:           'SET_NEW_NEXT',
  UPDATE_HEAD:            'UPDATE_HEAD',
  TRAVERSE_TO_TAIL:       'TRAVERSE_TO_TAIL',
  ATTACH_TO_TAIL:         'ATTACH_TO_TAIL',
  TRAVERSE_TO_INDEX:      'TRAVERSE_TO_INDEX',
  WIRE_NEW_NODE:          'WIRE_NEW_NODE',
  INDEX_OUT_OF_BOUNDS:    'INDEX_OUT_OF_BOUNDS',

  // Delete
  IDENTIFY_HEAD_DELETE:   'IDENTIFY_HEAD_DELETE',
  ADVANCE_HEAD:           'ADVANCE_HEAD',
  TRAVERSE_TO_PREV:       'TRAVERSE_TO_PREV',
  IDENTIFY_TARGET:        'IDENTIFY_TARGET',
  BYPASS_NODE:            'BYPASS_NODE',
  REMOVE_NODE:            'REMOVE_NODE',
  VALUE_NOT_FOUND:        'VALUE_NOT_FOUND',

  // Search
  COMPARE_VALUE:          'COMPARE_VALUE',
  VALUE_FOUND:            'VALUE_FOUND',

  // Reverse
  INIT_POINTERS:          'INIT_POINTERS',
  SAVE_NEXT:              'SAVE_NEXT',
  REVERSE_POINTER:        'REVERSE_POINTER',
  ADVANCE_POINTERS:       'ADVANCE_POINTERS',
  UPDATE_HEAD_TO_PREV:    'UPDATE_HEAD_TO_PREV',
});