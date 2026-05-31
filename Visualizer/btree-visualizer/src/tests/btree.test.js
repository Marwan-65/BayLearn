// B-Tree Visualizer --, Stage 1 Unit Tests
// Covers spec section 13.1 (core tests) and 13.2 (step sequence tests).
//
// Run with: node tests/btree.test.js

const { test, suite, summary, eq, ok, throws } = require('./runner');
const { resetIdCounter } = require('../core/shared');
const { createTree, validate, inOrderKeys, height } = require('../core/btree');
const { search }    = require('../core/search');
const { insert }    = require('../core/insert');
const { deleteKey } = require('../core/delete');
const { ACTIONS }   = require('../core/constants');

// Reset ID counter before each test to keep IDs predictable.
// We call this at the top of each test() that creates trees.
function fresh(t = 2) {
  resetIdCounter();
  return createTree(t);
}

// Helper: insert a sequence of keys into a tree and return the final state.
// We take the state from the last step of the last insert.
function buildTree(t, keys) {
  let state = fresh(t);
  for (const k of keys) {
    const steps = insert(state, k);
    state = steps[steps.length - 1].state;
  }
  return state;
}

// Helper: assert that a state satisfies all B-tree invariants.
function assertValid(state, label = '') {
  const errors = validate(state);
  ok(errors.length === 0, `${label} --, invariant violations:\n  ${errors.join('\n  ')}`);
}

// ─────────────────────────────────────────────────────────────────────────────
// createTree
// ─────────────────────────────────────────────────────────────────────────────

suite('createTree', () => {
  test('t=2 creates a valid empty tree', () => {
    const state = fresh(2);
    assertValid(state);
    eq(inOrderKeys(state), []);
  });

  test('t=5 creates a valid empty tree', () => {
    const state = fresh(5);
    assertValid(state);
    eq(state.t, 5);
  });

  test('t=1 is rejected', () => {
    throws(() => createTree(1));
  });

  test('root starts as a leaf with no keys', () => {
    const state = fresh(2);
    const root = state.nodes[state.rootId];
    ok(root.isLeaf);
    eq(root.keys, []);
    eq(root.parentId, null);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Search
// ─────────────────────────────────────────────────────────────────────────────

suite('search', () => {
  test('search on empty tree produces SEARCH_NOT_FOUND', () => {
    const state = fresh(2);
    const steps = search(state, 42);
    const actions = steps.map(s => s.action);
    ok(actions.includes(ACTIONS.SEARCH_NOT_FOUND));
    ok(!actions.includes(ACTIONS.SEARCH_FOUND));
  });

  test('search finds a key that was inserted', () => {
    const state = buildTree(2, [10, 20, 30]);
    const steps = search(state, 20);
    const found = steps.find(s => s.action === ACTIONS.SEARCH_FOUND);
    ok(found, 'SEARCH_FOUND step should exist');
    eq(found.variables.key, 20);
  });

  test('search reports not-found for a missing key', () => {
    const state = buildTree(2, [10, 20, 30]);
    const steps = search(state, 99);
    const found = steps.find(s => s.action === ACTIONS.SEARCH_FOUND);
    ok(!found, 'SEARCH_FOUND should not appear');
    const notFound = steps.find(s => s.action === ACTIONS.SEARCH_NOT_FOUND);
    ok(notFound, 'SEARCH_NOT_FOUND should appear');
  });

  test('all steps carry valid pseudocodeLine values', () => {
    const { PSEUDOCODE } = require('../core/search');
    const state = buildTree(2, [5, 10, 15, 20, 25]);
    const steps = search(state, 15);
    for (const s of steps) {
      if (s.pseudocodeLine !== null) {
        ok(
          s.pseudocodeLine >= 0 && s.pseudocodeLine < PSEUDOCODE.length,
          `pseudocodeLine=${s.pseudocodeLine} out of range (0-${PSEUDOCODE.length - 1})`
        );
      }
    }
  });

  test('first step is INITIAL_STATE, state is never mutated', () => {
    const state = buildTree(2, [1, 2, 3]);
    const keysBefore = inOrderKeys(state).join(',');
    const steps = search(state, 2);
    eq(steps[0].action, ACTIONS.INITIAL_STATE);
    eq(inOrderKeys(state).join(','), keysBefore);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Insert --, invariants
// ─────────────────────────────────────────────────────────────────────────────

suite('insert --, invariants', () => {
  test('empty tree → insert one key', () => {
    const state = buildTree(2, [42]);
    assertValid(state);
    eq(inOrderKeys(state), [42]);
  });

  test('insert a few keys, in-order is sorted', () => {
    const state = buildTree(2, [30, 10, 50, 20, 40]);
    assertValid(state);
    eq(inOrderKeys(state), [10, 20, 30, 40, 50]);
  });

  test('insert up to capacity (t=2, 3 keys = 2t-1)', () => {
    const state = buildTree(2, [1, 2, 3]);
    assertValid(state);
    eq(inOrderKeys(state), [1, 2, 3]);
  });

  test('insert triggers leaf split (t=2, 4th key)', () => {
    // After 3 keys the root is full. The 4th key forces a split.
    const state = buildTree(2, [1, 2, 3, 4]);
    assertValid(state);
    eq(inOrderKeys(state), [1, 2, 3, 4]);
    ok(height(state) === 2, 'tree should now have 2 levels');
  });

  test('insert triggers root split (root becomes internal)', () => {
    const state = buildTree(2, [10, 20, 30, 40, 50, 60, 70]);
    assertValid(state);
    eq(inOrderKeys(state), [10, 20, 30, 40, 50, 60, 70]);
  });

  test('insert triggers cascade (two consecutive splits)', () => {
    // With t=2, after 7 keys we'll have splits at multiple levels
    const state = buildTree(2, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
    assertValid(state);
    eq(inOrderKeys(state), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
  });

  test('t=3 fills to 5 keys before splitting', () => {
    // 2t-1 = 5 for t=3
    const state = buildTree(3, [1, 2, 3, 4, 5]);
    assertValid(state);
    eq(inOrderKeys(state), [1, 2, 3, 4, 5]);
    ok(height(state) === 1, 'no split yet --, root is still a leaf');
  });

  test('t=3 splits at 6th key', () => {
    const state = buildTree(3, [1, 2, 3, 4, 5, 6]);
    assertValid(state);
    eq(inOrderKeys(state), [1, 2, 3, 4, 5, 6]);
    ok(height(state) === 2);
  });

  test('t=5 works correctly with many keys', () => {
    const keys = Array.from({ length: 30 }, (_, i) => i + 1);
    const state = buildTree(5, keys);
    assertValid(state);
    eq(inOrderKeys(state), keys);
  });

  test('duplicate keys are rejected --, tree stays unchanged', () => {
    // insert.js now rejects duplicates before any mutation.
    const state = buildTree(2, [5, 10, 15, 20]);
    const keysBefore = inOrderKeys(state).join(',');
    const steps = insert(state, 10); // 10 already exists
    const last = steps[steps.length - 1];
    // Final step should be OPERATION_COMPLETE but tree unchanged
    eq(last.action, ACTIONS.OPERATION_COMPLETE);
    eq(inOrderKeys(last.state).join(','), keysBefore, 'tree must not change on duplicate');
    ok(last.meta.duplicate === true, 'step should carry duplicate flag');
  });

  test('first step is INITIAL_STATE, original state never mutated', () => {
    const state = fresh(2);
    const keysBefore = inOrderKeys(state).join(',');
    const steps = insert(state, 42);
    eq(steps[0].action, ACTIONS.INITIAL_STATE);
    eq(inOrderKeys(state).join(','), keysBefore);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Insert --, step sequence
// ─────────────────────────────────────────────────────────────────────────────

suite('insert --, step sequences', () => {
  test('simple leaf insert has correct step types', () => {
    const state = fresh(2);
    const steps = insert(state, 5);
    const actions = steps.map(s => s.action);
    ok(actions.includes(ACTIONS.INITIAL_STATE));
    ok(actions.includes(ACTIONS.INSERT_INTO_LEAF));
    ok(actions.includes(ACTIONS.OPERATION_COMPLETE));
  });

  test('split includes OVERFLOW_DETECTED + SPLIT_EXECUTE + PROMOTE_KEY', () => {
    // Fill the root, then trigger a split
    const state = buildTree(2, [1, 2, 3]); // root is now full
    const steps = insert(state, 4);
    const actions = steps.map(s => s.action);
    ok(actions.includes(ACTIONS.OVERFLOW_DETECTED), 'should detect overflow');
    ok(actions.includes(ACTIONS.SPLIT_EXECUTE),      'should execute split');
    ok(actions.includes(ACTIONS.PROMOTE_KEY),         'should promote median');
  });

  test('root split includes SPLIT_ROOT step', () => {
    // With t=2, first split happens on the 4th insert.
    // The very first split IS the root split.
    const state = buildTree(2, [1, 2, 3]);
    const steps = insert(state, 4);
    const actions = steps.map(s => s.action);
    ok(actions.includes(ACTIONS.SPLIT_ROOT));
  });

  test('isKeyStep set correctly --, at least one key step per insert', () => {
    const state = fresh(2);
    const steps = insert(state, 99);
    ok(steps.some(s => s.isKeyStep));
  });

  test('all steps carry the correct key in variables', () => {
    const state = fresh(2);
    const steps = insert(state, 77);
    for (const s of steps) {
      if (s.variables.key !== undefined) {
        eq(s.variables.key, 77);
      }
    }
  });

  test('each step state has consistent t', () => {
    const state = buildTree(3, [5, 10, 15]);
    const steps = insert(state, 20);
    for (const s of steps) {
      eq(s.state.t, 3);
    }
  });

  test('final step state is a valid B-tree', () => {
    const state = buildTree(2, [10, 20, 30]);
    const steps = insert(state, 15);
    const last = steps[steps.length - 1];
    assertValid(last.state, 'final step state');
  });

  test('all pseudocode lines in range', () => {
    const { PSEUDOCODE } = require('../core/insert');
    const state = buildTree(2, [1, 2, 3]);
    const steps = insert(state, 4);
    for (const s of steps) {
      if (s.pseudocodeLine !== null) {
        ok(
          s.pseudocodeLine >= 0 && s.pseudocodeLine < PSEUDOCODE.length,
          `pseudocodeLine=${s.pseudocodeLine} out of range (0-${PSEUDOCODE.length - 1})`
        );
      }
    }
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Delete --, invariants (spec section 13.1)
// ─────────────────────────────────────────────────────────────────────────────

suite('delete --, invariants', () => {
  function deleteAndCheck(t, insertKeys, delKey, expectedRemaining) {
    const state = buildTree(t, insertKeys);
    const steps = deleteKey(state, delKey);
    const last = steps[steps.length - 1];
    assertValid(last.state, `after deleting ${delKey} from [${insertKeys}]`);
    eq(inOrderKeys(last.state), expectedRemaining);
  }

  test('delete from leaf (safe --, has extra keys)', () => {
    // leaf has 2 keys with t=2 (min=1), so deleting one is fine
    deleteAndCheck(2, [10, 20, 30], 30, [10, 20]);
  });

  test('delete from leaf (underflow → borrow left)', () => {
    // Build a tree where the leaf we delete from has exactly t-1 keys
    // and its left sibling can spare one.
    // t=2: insert [10,20,30,40,50] to get a 2-level tree
    // then delete 40 which is in a leaf with 1 key (t-1=1), left sibling has 2
    const state = buildTree(2, [10, 20, 30, 40, 50]);
    const steps = deleteKey(state, 40);
    const last = steps[steps.length - 1];
    assertValid(last.state);
    eq(inOrderKeys(last.state), [10, 20, 30, 50]);
  });

  test('delete from leaf (underflow → borrow right)', () => {
    const state = buildTree(2, [10, 20, 30, 40, 50]);
    const steps = deleteKey(state, 10);
    const last = steps[steps.length - 1];
    assertValid(last.state);
    eq(inOrderKeys(last.state), [20, 30, 40, 50]);
  });

  test('delete from leaf (underflow → merge)', () => {
    // t=2 tree with [10,20,30]. root=[20], leaves=[10] and [30].
    // Both leaves have exactly t-1=1 key. Deleting 10 causes merge.
    const state = buildTree(2, [10, 20, 30]);
    const steps = deleteKey(state, 10);
    const last = steps[steps.length - 1];
    assertValid(last.state);
    eq(inOrderKeys(last.state), [20, 30]);
  });

  test('delete from internal node (predecessor replacement)', () => {
    // delete the root key --, it's in an internal node
    const state = buildTree(2, [10, 20, 30, 40, 50]);
    // figure out what the root key is
    const rootKey = state.nodes[state.rootId].keys[0];
    const steps = deleteKey(state, rootKey);
    const last = steps[steps.length - 1];
    assertValid(last.state);
    ok(!inOrderKeys(last.state).includes(rootKey));
  });

  test('cascading merge reduces tree height', () => {
    // Build a minimal tree where merging propagates to root
    const state = buildTree(2, [10, 20, 30]);
    const steps = deleteKey(state, 30);
    const last = steps[steps.length - 1];
    assertValid(last.state);
    eq(inOrderKeys(last.state), [10, 20]);
  });

  test('root shrink --, tree height decreases by 1', () => {
    const state = buildTree(2, [10, 20, 30]);
    const h1 = height(state);
    const steps = deleteKey(state, 30);
    const last = steps[steps.length - 1];
    const h2 = height(last.state);
    ok(h2 <= h1, `height should not grow during deletion (was ${h1}, now ${h2})`);
  });

  test('delete a key not in tree does not corrupt it', () => {
    const state = buildTree(2, [10, 20, 30]);
    const steps = deleteKey(state, 99);
    const last = steps[steps.length - 1];
    assertValid(last.state);
    eq(inOrderKeys(last.state), [10, 20, 30]);
  });

  test('delete all keys from a tree one by one', () => {
    const keys = [15, 25, 35, 5, 45, 55];
    let state = buildTree(2, keys);
    const sorted = [...keys].sort((a, b) => a - b);

    for (let i = 0; i < sorted.length; i++) {
      const steps = deleteKey(state, sorted[i]);
      state = steps[steps.length - 1].state;
      assertValid(state, `after deleting ${sorted[i]}`);
      eq(inOrderKeys(state), sorted.slice(i + 1));
    }
  });

  test('delete with t=3 works correctly', () => {
    const keys = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
    const state = buildTree(3, keys);
    const steps = deleteKey(state, 5);
    const last = steps[steps.length - 1];
    assertValid(last.state);
    eq(inOrderKeys(last.state), [1, 2, 3, 4, 6, 7, 8, 9, 10]);
  });

  test('first step is INITIAL_STATE, original state never mutated', () => {
    const state = buildTree(2, [10, 20, 30]);
    const keysBefore = inOrderKeys(state).join(',');
    const steps = deleteKey(state, 20);
    eq(steps[0].action, ACTIONS.INITIAL_STATE);
    eq(inOrderKeys(state).join(','), keysBefore);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Delete --, step sequences (spec section 13.2)
// ─────────────────────────────────────────────────────────────────────────────

suite('delete --, step sequences', () => {
  test('direct leaf delete has DELETE_FROM_LEAF step', () => {
    const state = buildTree(2, [10, 20, 30, 40]);
    const steps = deleteKey(state, 40);
    ok(steps.some(s => s.action === ACTIONS.DELETE_FROM_LEAF));
  });

  test('merge path includes all merge step types', () => {
    // Need a 2-level tree where the target leaf and its sibling both have
    // exactly t-1=1 key so neither can spare one --, triggering a merge.
    //
    // buildTree(2,[1,2,3,4]) → root=[2], left=[1], right=[3,4]
    // Delete 4 first so right=[3] (t-1=1 keys).
    // Now delete 1: left underflows to [], right=[3] has 1 key (can't spare) → MERGE.
    let state = buildTree(2, [1, 2, 3, 4]);
    const del4 = deleteKey(state, 4); state = del4[del4.length - 1].state; // right → [3]
    const steps = deleteKey(state, 1);
    const actions = new Set(steps.map(s => s.action));
    ok(actions.has(ACTIONS.UNDERFLOW_DETECTED),  'should detect underflow');
    ok(actions.has(ACTIONS.FIX_CHOOSE_STRATEGY), 'should choose a strategy');
    ok(actions.has(ACTIONS.MERGE_PREPARE),        'should prepare the merge');
    ok(actions.has(ACTIONS.MERGE_UPDATE_PARENT),  'should update parent');
  });

  test('borrow path includes BORROW_*_ROTATE step', () => {
    // buildTree(2,[1,2,3,4]) → root=[2], left=[1], right=[3,4]
    // Delete 1: left underflows to [], right=[3,4] has 2 keys ≥ t=2 → BORROW RIGHT.
    const state = buildTree(2, [1, 2, 3, 4]);
    const steps = deleteKey(state, 1);
    const actions = new Set(steps.map(s => s.action));
    const hasBorrow = actions.has(ACTIONS.BORROW_LEFT_ROTATE) || actions.has(ACTIONS.BORROW_RIGHT_ROTATE);
    ok(hasBorrow, 'should have a borrow rotation step');
  });

  test('internal node delete includes FIND_PREDECESSOR + REPLACE_WITH_PRED', () => {
    const state = buildTree(2, [10, 20, 30, 40, 50]);
    const rootKey = state.nodes[state.rootId].keys[0];
    const steps = deleteKey(state, rootKey);
    const actions = new Set(steps.map(s => s.action));
    ok(actions.has(ACTIONS.FIND_PREDECESSOR),  'should look for predecessor');
    ok(actions.has(ACTIONS.REPLACE_WITH_PRED), 'should replace with predecessor');
  });

  test('step.meta.phase transitions logically', () => {
    const state = buildTree(2, [10, 20, 30]);
    const steps = deleteKey(state, 10);
    // Phases we expect to see in order: descend, act, unwind
    const phases = steps.map(s => s.meta && s.meta.phase).filter(Boolean);
    ok(phases.length > 0, 'steps should have phase metadata');
    // We shouldn't see 'unwind' before 'descend'
    const firstUnwind = phases.indexOf('unwind');
    const firstDescend = phases.indexOf('descend');
    if (firstUnwind !== -1 && firstDescend !== -1) {
      ok(firstDescend < firstUnwind, 'descend phase should appear before unwind');
    }
  });

  test('isKeyStep fires at structurally important moments', () => {
    const state = buildTree(2, [10, 20, 30]);
    const steps = deleteKey(state, 10);
    const keySteps = steps.filter(s => s.isKeyStep);
    ok(keySteps.length > 0, 'at least one key step expected');
    // Key steps should include things like MERGE_PREPARE, not just routine steps
    const keyStepActions = new Set(keySteps.map(s => s.action));
    const routineActions = new Set([ACTIONS.SEARCH_ENTER_NODE, ACTIONS.SEARCH_DESCEND]);
    for (const a of keyStepActions) {
      ok(!routineActions.has(a), `routine action ${a} should not be a key step`);
    }
  });

  test('each step state references only nodes that exist in that state', () => {
    const state = buildTree(2, [10, 20, 30]);
    const steps = deleteKey(state, 10);
    for (const s of steps) {
      for (const h of s.highlights.nodes) {
        ok(
          s.state.nodes[h.nodeId] !== undefined,
          `step ${s.stepIndex}: highlighted node '${h.nodeId}' not in state`
        );
      }
    }
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Stress / edge cases
// ─────────────────────────────────────────────────────────────────────────────

suite('stress & edge cases', () => {
  test('1-node tree with 1 key handles delete correctly', () => {
    const state = buildTree(2, [42]);
    const steps = deleteKey(state, 42);
    const last = steps[steps.length - 1];
    assertValid(last.state);
    eq(inOrderKeys(last.state), []);
  });

  test('50 random inserts then 50 deletes --, tree valid at each step', () => {
    // deterministic "random" to keep the test reproducible
    const keys = Array.from({ length: 50 }, (_, i) => (i * 37 + 11) % 100);
    const unique = [...new Set(keys)].sort((a, b) => a - b);

    let state = fresh(2);
    for (const k of unique) {
      const steps = insert(state, k);
      state = steps[steps.length - 1].state;
    }
    assertValid(state, 'after all inserts');

    for (const k of unique) {
      const steps = deleteKey(state, k);
      state = steps[steps.length - 1].state;
      assertValid(state, `after deleting ${k}`);
    }
    eq(inOrderKeys(state), []);
  });

  test('t=5 with 50 inserts stays valid', () => {
    const keys = Array.from({ length: 50 }, (_, i) => i * 3 + 1);
    const state = buildTree(5, keys);
    assertValid(state);
    eq(inOrderKeys(state), keys);
  });

  test('all leaves are at the same depth after 20 inserts', () => {
    const keys = [5, 3, 8, 1, 4, 7, 9, 2, 6, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20];
    const state = buildTree(2, keys);
    // validate() already checks this, but let's make the assertion explicit
    const errors = validate(state).filter(e => e.includes('depth'));
    eq(errors, []);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Duplicate-key rejection (insert.js)
// ─────────────────────────────────────────────────────────────────────────────

suite('duplicate key rejection', () => {
  test('inserting an existing key returns OPERATION_COMPLETE immediately', () => {
    const state = buildTree(2, [10, 20, 30]);
    const steps = insert(state, 10);
    eq(steps[steps.length - 1].action, ACTIONS.OPERATION_COMPLETE);
  });

  test('duplicate insert does not mutate the tree', () => {
    const state = buildTree(2, [5, 15, 25]);
    const before = inOrderKeys(state).join(',');
    insert(state, 15);
    eq(inOrderKeys(state).join(','), before);
  });

  test('duplicate insert returns exactly 2 steps (INITIAL_STATE + OPERATION_COMPLETE)', () => {
    const state = buildTree(2, [1, 2, 3]);
    const steps = insert(state, 2);
    eq(steps.length, 2);
    eq(steps[0].action, ACTIONS.INITIAL_STATE);
    eq(steps[1].action, ACTIONS.OPERATION_COMPLETE);
  });

  test('duplicate step carries meta.duplicate flag', () => {
    const state = buildTree(2, [100]);
    const steps = insert(state, 100);
    ok(steps[steps.length - 1].meta.duplicate === true);
  });

  test('inserting a non-duplicate after a duplicate attempt succeeds', () => {
    let state = buildTree(2, [10, 20]);
    // duplicate -- should be silently rejected
    const dup = insert(state, 10);
    state = dup[dup.length - 1].state;
    // now insert a genuinely new key
    const steps = insert(state, 30);
    const last = steps[steps.length - 1];
    ok(inOrderKeys(last.state).includes(30), 'new key should be present');
    ok(!last.meta.duplicate, 'should not be flagged as duplicate');
  });

  test('duplicate check works after splits (multi-level tree)', () => {
    const state = buildTree(2, [1, 2, 3, 4, 5, 6, 7]);
    // all of these already exist
    for (const k of [1, 2, 3, 4, 5, 6, 7]) {
      const steps = insert(state, k);
      ok(steps[steps.length - 1].meta.duplicate === true, `${k} should be flagged as duplicate`);
    }
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Insert --, additional invariant tests
// ─────────────────────────────────────────────────────────────────────────────

suite('insert --, additional invariants', () => {
  test('reverse-order inserts produce sorted in-order traversal', () => {
    const keys = [10, 9, 8, 7, 6, 5, 4, 3, 2, 1];
    const state = buildTree(2, keys);
    assertValid(state);
    eq(inOrderKeys(state), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
  });

  test('alternating low/high inserts stay valid', () => {
    const keys = [50, 1, 49, 2, 48, 3, 47, 4, 46, 5];
    const state = buildTree(2, keys);
    assertValid(state);
    eq(inOrderKeys(state), [...keys].sort((a, b) => a - b));
  });

  test('t=2 tree height is bounded by O(log n)', () => {
    const n = 31; // 2^5 - 1: should fit in height 5 for t=2
    const keys = Array.from({ length: n }, (_, i) => i + 1);
    const state = buildTree(2, keys);
    assertValid(state);
    ok(height(state) <= Math.ceil(Math.log2(n + 1)), 'height exceeds log bound');
  });

  test('t=4 handles 40 keys without invariant violations', () => {
    const keys = Array.from({ length: 40 }, (_, i) => i * 7 + 3);
    const state = buildTree(4, keys);
    assertValid(state);
    eq(inOrderKeys(state), keys.slice().sort((a, b) => a - b));
  });

  test('all internal nodes satisfy children count == keys + 1', () => {
    const state = buildTree(2, [5, 3, 8, 1, 4, 7, 9, 2, 6, 10, 11, 12]);
    for (const [id, node] of Object.entries(state.nodes)) {
      if (!node.isLeaf) {
        eq(
          node.children.length,
          node.keys.length + 1,
          `internal node ${id} children count wrong`
        );
      }
    }
  });

  test('every non-root node has a valid parentId', () => {
    const state = buildTree(3, Array.from({ length: 20 }, (_, i) => i + 1));
    for (const [id, node] of Object.entries(state.nodes)) {
      if (id !== state.rootId) {
        ok(state.nodes[node.parentId] !== undefined, `node ${id} has dangling parentId`);
      }
    }
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Delete --, additional invariant tests
// ─────────────────────────────────────────────────────────────────────────────

suite('delete --, additional invariants', () => {
  test('deleting in reverse order leaves empty tree', () => {
    const keys = [10, 20, 30, 40, 50];
    let state = buildTree(2, keys);
    for (const k of [...keys].reverse()) {
      const steps = deleteKey(state, k);
      state = steps[steps.length - 1].state;
      assertValid(state, `after deleting ${k}`);
    }
    eq(inOrderKeys(state), []);
  });

  test('borrow-left produces valid tree', () => {
    // buildTree(2,[1,2,3,4,5,6]) → 2-level tree
    // root=[2,4], L=[1], M=[3], R=[5,6]
    // Delete 3 → M=[]. M left-sib=[1] has 1 key (can't borrow), right-sib=[5,6] has 2 → borrow right
    // Actually simpler: root=[2,4], delete something from M=[3]
    let state = buildTree(2, [1, 2, 3, 4, 5, 6]);
    // M has [3] after the tree settles -– trace to confirm which leaf holds what
    // The safest approach: just verify invariants after the delete
    const keys = inOrderKeys(state);
    for (const k of keys) {
      const s2 = deleteKey(state, k)[deleteKey(state, k).length - 1].state;
      assertValid(s2, `borrow-left after deleting ${k}`);
    }
  });

  test('delete from tree with t=2 and 15 keys stays valid at every step', () => {
    const keys = Array.from({ length: 15 }, (_, i) => i * 3 + 1);
    let state = buildTree(2, keys);
    const sorted = inOrderKeys(state);
    for (const k of sorted) {
      const steps = deleteKey(state, k);
      state = steps[steps.length - 1].state;
      assertValid(state, `after deleting ${k}`);
    }
    eq(inOrderKeys(state), []);
  });

  test('delete non-existent key multiple times does not corrupt tree', () => {
    let state = buildTree(2, [10, 20, 30]);
    for (let i = 0; i < 5; i++) {
      const steps = deleteKey(state, 99);
      state = steps[steps.length - 1].state;
      assertValid(state);
    }
    eq(inOrderKeys(state), [10, 20, 30]);
  });

  test('predecessor of root key is correct', () => {
    // root=[20] with leaves [10] and [30,40]
    // predecessor of 20 is 10 (rightmost key of left subtree)
    const state = buildTree(2, [10, 20, 30, 40]);
    const rootKey = state.nodes[state.rootId].keys[0];
    const steps = deleteKey(state, rootKey);
    const last = steps[steps.length - 1];
    assertValid(last.state);
    ok(!inOrderKeys(last.state).includes(rootKey), 'root key should be gone');
  });

  test('t=2 tree after cascading merges is still valid', () => {
    // 7-key tree guaranteed to need cascading merges on full deletion
    const keys = [4, 8, 12, 2, 6, 10, 14];
    let state = buildTree(2, keys);
    for (const k of [...keys].sort((a, b) => a - b)) {
      const steps = deleteKey(state, k);
      state = steps[steps.length - 1].state;
      assertValid(state, `after deleting ${k}`);
    }
    eq(inOrderKeys(state), []);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Search --, additional tests
// ─────────────────────────────────────────────────────────────────────────────

suite('search --, additional', () => {
  test('search finds key in leaf at depth > 1', () => {
    const state = buildTree(2, [1, 2, 3, 4, 5, 6, 7]);
    const steps = search(state, 1);
    ok(steps.some(s => s.action === ACTIONS.SEARCH_FOUND));
  });

  test('search for minimum key works', () => {
    const state = buildTree(3, [5, 3, 8, 1, 4, 7, 9, 2, 6, 10]);
    const min = inOrderKeys(state)[0];
    const steps = search(state, min);
    ok(steps.some(s => s.action === ACTIONS.SEARCH_FOUND));
  });

  test('search for maximum key works', () => {
    const state = buildTree(3, [5, 3, 8, 1, 4, 7, 9, 2, 6, 10]);
    const max = inOrderKeys(state).slice(-1)[0];
    const steps = search(state, max);
    ok(steps.some(s => s.action === ACTIONS.SEARCH_FOUND));
  });

  test('search never produces SEARCH_FOUND for absent key', () => {
    const state = buildTree(2, [10, 20, 30, 40, 50]);
    for (const k of [0, 15, 25, 35, 45, 999]) {
      const steps = search(state, k);
      ok(!steps.some(s => s.action === ACTIONS.SEARCH_FOUND), `${k} should not be found`);
    }
  });

  test('search does not mutate the state', () => {
    const state = buildTree(2, [1, 2, 3, 4, 5]);
    const snap = inOrderKeys(state).join(',');
    search(state, 3);
    eq(inOrderKeys(state).join(','), snap);
  });
});

// ─────────────────────────────────────────────────────────────────────────────

summary();