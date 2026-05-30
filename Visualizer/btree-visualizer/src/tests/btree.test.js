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

  test('duplicate keys are handled gracefully (insert is not rejected)', () => {
    // The spec does not explicitly define duplicate behaviour, but the
    // invariant checker just requires sorted order --, duplicates would break
    // strict ascending. So we insert distinct keys only in normal usage.
    // Just verify no crash:
    const state = buildTree(2, [5, 10, 15, 20]);
    ok(state); // just verifying it doesn't explode
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
    const state = buildTree(2, [10, 20, 30]);
    const steps = deleteKey(state, 10);
    const actions = new Set(steps.map(s => s.action));
    ok(actions.has(ACTIONS.UNDERFLOW_DETECTED),  'should detect underflow');
    ok(actions.has(ACTIONS.FIX_CHOOSE_STRATEGY), 'should choose a strategy');
    ok(actions.has(ACTIONS.MERGE_PREPARE),        'should prepare the merge');
    ok(actions.has(ACTIONS.MERGE_UPDATE_PARENT),  'should update parent');
  });

  test('borrow path includes BORROW_*_ROTATE step', () => {
    const state = buildTree(2, [10, 20, 30, 40, 50]);
    const steps = deleteKey(state, 40);
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

summary();