// All action, node, key, and edge role constants used across the visualizer.
// Keep this as the single source of truth --, never hardcode these strings elsewhere.

const ACTIONS = {
  // lifecycle
  INITIAL_STATE:        'INITIAL_STATE',
  OPERATION_COMPLETE:   'OPERATION_COMPLETE',

  // search
  SEARCH_ENTER_NODE:    'SEARCH_ENTER_NODE',
  SEARCH_COMPARE_KEY:   'SEARCH_COMPARE_KEY',
  SEARCH_GO_LEFT:       'SEARCH_GO_LEFT',
  SEARCH_GO_RIGHT:      'SEARCH_GO_RIGHT',
  SEARCH_DESCEND:       'SEARCH_DESCEND',
  SEARCH_FOUND:         'SEARCH_FOUND',
  SEARCH_NOT_FOUND:     'SEARCH_NOT_FOUND',

  // insert
  INSERT_INTO_LEAF:     'INSERT_INTO_LEAF',
  INSERT_SHIFT_KEYS:    'INSERT_SHIFT_KEYS',
  OVERFLOW_DETECTED:    'OVERFLOW_DETECTED',
  SPLIT_PREPARE:        'SPLIT_PREPARE',
  SPLIT_EXECUTE:        'SPLIT_EXECUTE',
  PROMOTE_KEY:          'PROMOTE_KEY',
  PROMOTE_INTO_PARENT:  'PROMOTE_INTO_PARENT',
  SPLIT_ROOT:           'SPLIT_ROOT',
  EDGE_REROUTE:         'EDGE_REROUTE',

  // delete
  DELETE_FIND_KEY:          'DELETE_FIND_KEY',
  DELETE_FROM_LEAF:         'DELETE_FROM_LEAF',
  DELETE_SHIFT_KEYS:        'DELETE_SHIFT_KEYS',
  FIND_PREDECESSOR:         'FIND_PREDECESSOR',
  REPLACE_WITH_PRED:        'REPLACE_WITH_PRED',
  UNDERFLOW_DETECTED:       'UNDERFLOW_DETECTED',
  FIX_CHOOSE_STRATEGY:      'FIX_CHOOSE_STRATEGY',
  BORROW_LEFT_PREPARE:      'BORROW_LEFT_PREPARE',
  BORROW_LEFT_ROTATE:       'BORROW_LEFT_ROTATE',
  BORROW_RIGHT_PREPARE:     'BORROW_RIGHT_PREPARE',
  BORROW_RIGHT_ROTATE:      'BORROW_RIGHT_ROTATE',
  MERGE_PREPARE:            'MERGE_PREPARE',
  MERGE_PULL_SEPARATOR:     'MERGE_PULL_SEPARATOR',
  MERGE_ABSORB_KEYS:        'MERGE_ABSORB_KEYS',
  MERGE_ABSORB_CHILDREN:    'MERGE_ABSORB_CHILDREN',
  MERGE_REMOVE_NODE:        'MERGE_REMOVE_NODE',
  MERGE_UPDATE_PARENT:      'MERGE_UPDATE_PARENT',
  ROOT_SHRINK:              'ROOT_SHRINK',
};

const NODE_ROLES = {
  DEFAULT:       'default',
  ACTIVE:        'active',        // currently being visited (gold)
  PARENT:        'parent',        // parent of the active node (dimly gold)
  SPLIT_LEFT:    'split_left',    // left half of a split (green)
  SPLIT_RIGHT:   'split_right',   // right half of a split (green)
  MERGE_TARGET:  'merge_target',  // node receiving merged keys (blue)
  MERGE_SOURCE:  'merge_source',  // node being absorbed (red)
  SIBLING_LEFT:  'sibling_left',  // left sibling in a borrow (purple)
  SIBLING_RIGHT: 'sibling_right', // right sibling in a borrow (purple)
  OVERFLOW:      'overflow',      // node exceeding 2t-1 keys (red pulse)
  UNDERFLOW:     'underflow',     // node with < t-1 keys (orange pulse)
  DIM:           'dim',           // not involved in current step
};

const KEY_ROLES = {
  DEFAULT:     'default',
  COMPARING:   'comparing',   // being compared against the target key
  FOUND:       'found',       // the target key was located here
  INSERTING:   'inserting',   // being placed into a slot
  DELETING:    'deleting',    // being removed
  MEDIAN:      'median',      // median key in a split
  PROMOTING:   'promoting',   // key rising to the parent
  SEPARATOR:   'separator',   // parent key separating two siblings
  PREDECESSOR: 'predecessor', // predecessor key in a delete operation
};

const EDGE_ROLES = {
  DEFAULT:    'default',
  PATH:       'path',       // on the descent path
  NEW:        'new',        // newly created edge
  REMOVING:   'removing',   // edge being severed
  REROUTING:  'rerouting',  // edge changing target
};

module.exports = { ACTIONS, NODE_ROLES, KEY_ROLES, EDGE_ROLES };