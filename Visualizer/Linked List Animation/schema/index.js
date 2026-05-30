/**
 * SCHEMA / DATA LAYER
 *
 * Defines the shape of every data structure used by the visualizer.
 * Nothing in this file knows about rendering, animation, or operations.
 * It only defines what things ARE, not what they do.
 *
 * Key structures:
 *   Node       --, a single linked list node
 *   ListState  --, a full snapshot of the list at a moment in time
 *   Step       --, one animation frame: a state + rich metadata for the narrative layer
 *   Highlight  --, visual annotation for a node or pointer
 */

// ─── Node ────────────────────────────────────────────────────────────────────

/**
 * Creates a single linked list node.
 *
 * @param {string}      id    - Stable unique identifier (e.g. "n1", "n2")
 * @param {*}           value - The data payload (number, string, etc.)
 * @param {string|null} next  - ID of the next node, or null
 * @returns {Node}
 */
export function createNode(id, value, next = null) {
  return { id, value, next };
}

// ─── List State ──────────────────────────────────────────────────────────────

/**
 * Creates a new, empty list state.
 *
 * The state is a plain serialisable object --, no classes, no methods.
 * _nextId is an internal counter; the animation layer should never display it.
 *
 * @returns {ListState}
 */
export function createList() {
  return {
    nodes: {},   // { [id: string]: Node }  --, all nodes keyed by ID
    head: null,  // string | null            --, ID of the head node
    size: 0,     //  number                  --, number of nodes
    _nextId: 1,  // number (internal)        --, counter for ID generation
  };
}

/**
 * Builds a list state directly from an array of values.
 * Useful for test setup or seeding the visualizer from a data source.
 * This does NOT produce animation steps --, it is a one-shot constructor.
 *
 * @param {*[]} values
 * @returns {ListState}
 */
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

// ─── List State Accessors ────────────────────────────────────────────────────
// Pure read-only helpers. None of these mutate the list.

/**
 * Returns node IDs in traversal order (head → tail).
 * Includes a cycle guard so it is safe to call on malformed states.
 *
 * @param {ListState} list
 * @returns {string[]}
 */
export function getOrderedIds(list) {
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

/**
 * Returns the values of all nodes in traversal order.
 *
 * @param {ListState} list
 * @returns {*[]}
 */
export function toArray(list) {
  return getOrderedIds(list).map(id => list.nodes[id].value);
}

/**
 * Returns the ID of the tail node, or null if the list is empty.
 *
 * @param {ListState} list
 * @returns {string|null}
 */
export function getTailId(list) {
  const ids = getOrderedIds(list);
  return ids.length > 0 ? ids[ids.length - 1] : null;
}

/**
 * Returns the node at a given 0-based index, or null if out of bounds.
 *
 * @param {ListState} list
 * @param {number}    index
 * @returns {Node|null}
 */
export function getNodeAtIndex(list, index) {
  if (index < 0) return null;
  const ids = getOrderedIds(list);
  const id = ids[index] ?? null;
  return id ? list.nodes[id] : null;
}

/**
 * Returns the index (0-based) of the first node with the given value,
 * or -1 if not found.
 *
 * @param {ListState} list
 * @param {*}         value
 * @returns {number}
 */
export function indexOfValue(list, value) {
  const ids = getOrderedIds(list);
  return ids.findIndex(id => list.nodes[id].value === value);
}

// ─── Validation ──────────────────────────────────────────────────────────────

/**
 * Validates a list state. Useful for debugging the operation layer.
 *
 * @param {ListState} list
 * @returns {{ valid: boolean, errors: string[] }}
 */
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

// ─── Highlight Role Constants ─────────────────────────────────────────────────
//
// These string constants are the shared vocabulary between the operation layer
// and the animation/theme layers. The operation layer EMITS them; the animation
// layer READS them to decide colours, glows, etc.
//
// The theme module will map each role to a specific colour, but that mapping
// lives in the animation layer, not here.

/** Visual roles for nodes */
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

/** Visual roles for pointer arrows between nodes */
export const POINTER_ROLES = Object.freeze({
  DEFAULT:    'default',    // normal next-pointer
  TRAVERSING: 'traversing', // pointer being actively followed
  UPDATING:   'updating',   // pointer is about to be changed
  NEW:        'new',        // newly created pointer
  BREAKING:   'breaking',   // pointer being severed/nulled
});

// ─── Step Action Constants ────────────────────────────────────────────────────
//
// Machine-readable identifiers for what just happened in a step.
// The narrative layer can use these to decide UI behaviour beyond the
// explanation string (e.g. trigger a special animation, play a sound, etc.)

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