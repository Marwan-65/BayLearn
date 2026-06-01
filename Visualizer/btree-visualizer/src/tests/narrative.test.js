// Stage 7 Tests --, Narrative Layer
//
// Two sections:
//   1. Pure-Node  --, no DOM, tests all panel logic using a mock container
//   2. jsdom      --, real DOM, tests that innerHTML is populated correctly
//
// Run:
//   node src/tests/narrative.test.js
//
// For section 2:
//   npm install jsdom

'use strict';

const { test, suite, summary, eq, ok } = require('./runner');
const { ACTIONS, NODE_ROLES }           = require('../core/constants');
const { createTheme }                   = require('../animation/ThemeModule');

const THEME = createTheme();

// ─── Shared fixtures ──────────────────────────────────────────────────────────

function fakeState(overrides = {}) {
  return {
    t: 2,
    rootId: 'n1',
    nodes: {
      n1: { id: 'n1', keys: [20],     children: ['n2', 'n3'], isLeaf: false, parentId: null },
      n2: { id: 'n2', keys: [10],     children: [],           isLeaf: true,  parentId: 'n1' },
      n3: { id: 'n3', keys: [30, 40], children: [],           isLeaf: true,  parentId: 'n1' },
    },
    ...overrides,
  };
}

function fakeStep(action, overrides = {}) {
  return {
    stepIndex:      0,
    action,
    isKeyStep:      false,
    state:          fakeState(),
    highlights:     { nodes: [], keys: [], edges: [] },
    explanation:    'Key 20 found at index 0 in this node. Search complete.',
    pseudocodeLine: 2,
    variables:      { key: 20, t: 2 },
    meta:           { phase: 'descend', depth: 0, reason: null },
    ...overrides,
  };
}

// A container mock that tracks innerHTML assignments
function mockContainer() {
  let _html = '';
  return {
    get innerHTML() { return _html; },
    set innerHTML(v) { _html = v; },
    querySelector: () => null,
    style: { cssText: '' },
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Section 1a --, ExplanationPanel (no DOM)
// ─────────────────────────────────────────────────────────────────────────────

suite('ExplanationPanel --, construction and update', () => {
  const { ExplanationPanel } = require('../narrative/ExplanationPanel');

  test('constructs without throwing', () => {
    const c = mockContainer();
    const p = new ExplanationPanel(c, THEME);
    ok(p !== null);
  });

  test('initial render populates innerHTML', () => {
    const c = mockContainer();
    new ExplanationPanel(c, THEME);
    ok(c.innerHTML.length > 0, 'initial render should produce some HTML');
  });

  test('update() sets innerHTML with explanation text', () => {
    const c = mockContainer();
    const p = new ExplanationPanel(c, THEME);
    p.update(fakeStep(ACTIONS.SEARCH_FOUND, { explanation: 'Found it.' }));
    ok(c.innerHTML.includes('Found it.'), 'innerHTML should contain explanation text');
  });

  test('isKeyStep=true adds KEY STEP badge', () => {
    const c = mockContainer();
    const p = new ExplanationPanel(c, THEME);
    p.update(fakeStep(ACTIONS.SEARCH_FOUND, { isKeyStep: true }));
    ok(c.innerHTML.includes('KEY STEP'), 'KEY STEP badge should appear for key steps');
  });

  test('isKeyStep=false omits KEY STEP badge', () => {
    const c = mockContainer();
    const p = new ExplanationPanel(c, THEME);
    p.update(fakeStep(ACTIONS.SEARCH_ENTER_NODE, { isKeyStep: false }));
    ok(!c.innerHTML.includes('KEY STEP'), 'no KEY STEP badge for non-key steps');
  });

  test('act phase produces gold border colour', () => {
    const c = mockContainer();
    const p = new ExplanationPanel(c, THEME);
    p.update(fakeStep(ACTIONS.INSERT_INTO_LEAF, { meta: { phase: 'act', depth: 1 } }));
    // Gold colour used for act phase
    ok(c.innerHTML.includes('#d4a843'), 'act phase should use gold border');
  });

  test('descend phase produces blue border colour', () => {
    const c = mockContainer();
    const p = new ExplanationPanel(c, THEME);
    p.update(fakeStep(ACTIONS.SEARCH_ENTER_NODE, { meta: { phase: 'descend', depth: 0 } }));
    ok(c.innerHTML.includes('#60a5fa'), 'descend phase should use blue border');
  });

  test('reset() clears explanation', () => {
    const c = mockContainer();
    const p = new ExplanationPanel(c, THEME);
    p.update(fakeStep(ACTIONS.SEARCH_FOUND, { explanation: 'Found.' }));
    p.reset();
    ok(!c.innerHTML.includes('Found.'), 'reset should remove previous explanation');
  });

  test('destroy() empties container', () => {
    const c = mockContainer();
    const p = new ExplanationPanel(c, THEME);
    p.destroy();
    eq(c.innerHTML, '');
  });

  test('update() with every ACTIONS constant does not throw', () => {
    for (const action of Object.values(ACTIONS)) {
      const c = mockContainer();
      const p = new ExplanationPanel(c, THEME);
      p.update(fakeStep(action));
      ok(true, `ExplanationPanel should not throw for action ${action}`);
    }
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Section 1b --, PseudocodePanel
// ─────────────────────────────────────────────────────────────────────────────

suite('PseudocodePanel --, pseudocode content', () => {
  const { PseudocodePanel, PSEUDOCODES } = require('../narrative/PseudocodePanel');

  test('PSEUDOCODES has entries for search, insert, delete', () => {
    ok(Array.isArray(PSEUDOCODES.search) && PSEUDOCODES.search.length > 0);
    ok(Array.isArray(PSEUDOCODES.insert) && PSEUDOCODES.insert.length > 0);
    ok(Array.isArray(PSEUDOCODES.delete) && PSEUDOCODES.delete.length > 0);
  });

  test('search pseudocode starts with function search', () => {
    ok(PSEUDOCODES.search[0].includes('search'));
  });

  test('insert pseudocode contains splitChild', () => {
    ok(PSEUDOCODES.insert.some(l => l.includes('splitChild')));
  });

  test('delete pseudocode contains fixUnderflow', () => {
    ok(PSEUDOCODES.delete.some(l => l.includes('fixUnderflow')));
  });

  test('constructs without throwing', () => {
    const c = mockContainer();
    const p = new PseudocodePanel(c, THEME);
    ok(p !== null);
  });

  test('initial render shows placeholder when no op loaded', () => {
    const c = mockContainer();
    new PseudocodePanel(c, THEME);
    ok(c.innerHTML.includes('Select an operation'), 'should show placeholder initially');
  });

  test('loadOperation("search") renders pseudocode lines', () => {
    const c = mockContainer();
    const p = new PseudocodePanel(c, THEME);
    p.loadOperation('search');
    // Should include at least one line number
    ok(c.innerHTML.length > 100, 'should have content after loadOperation');
  });

  test('update() highlights the correct pseudocode line index', () => {
    const c = mockContainer();
    const p = new PseudocodePanel(c, THEME);
    p.loadOperation('search');
    p.update(fakeStep(ACTIONS.SEARCH_FOUND, { pseudocodeLine: 2 }));
    // The active line should have the gold highlight colour
    ok(c.innerHTML.includes(THEME.GOLD_LIGHT) || c.innerHTML.includes(THEME.GOLD_BG),
      'active line should be highlighted with gold colour');
  });

  test('update() with pseudocodeLine=null does not throw', () => {
    const c = mockContainer();
    const p = new PseudocodePanel(c, THEME);
    p.loadOperation('insert');
    p.update(fakeStep(ACTIONS.INSERT_INTO_LEAF, { pseudocodeLine: null }));
    ok(true);
  });

  test('phase label appears in rendered HTML after update', () => {
    const c = mockContainer();
    const p = new PseudocodePanel(c, THEME);
    p.loadOperation('delete');
    p.update(fakeStep(ACTIONS.DELETE_FROM_LEAF, { meta: { phase: 'act', depth: 1 } }));
    ok(c.innerHTML.includes('ACT'), 'phase label ACT should appear');
  });

  test('DESCEND label appears for descend phase', () => {
    const c = mockContainer();
    const p = new PseudocodePanel(c, THEME);
    p.loadOperation('search');
    p.update(fakeStep(ACTIONS.SEARCH_ENTER_NODE, { meta: { phase: 'descend', depth: 0 } }));
    ok(c.innerHTML.includes('DESCEND'), 'DESCEND label should appear');
  });

  test('destroy() empties container', () => {
    const c = mockContainer();
    const p = new PseudocodePanel(c, THEME);
    p.destroy();
    eq(c.innerHTML, '');
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Section 1c --, VariableInspector
// ─────────────────────────────────────────────────────────────────────────────

suite('VariableInspector --, variable rendering and resolution', () => {
  const { VariableInspector } = require('../narrative/VariableInspector');

  test('constructs without throwing', () => {
    const c = mockContainer();
    const v = new VariableInspector(c, THEME);
    ok(v !== null);
  });

  test('shows placeholder when no variables', () => {
    const c = mockContainer();
    const v = new VariableInspector(c, THEME);
    v.update(fakeStep(ACTIONS.INITIAL_STATE, { variables: {} }));
    ok(c.innerHTML.includes('No variables'), 'empty variables should show placeholder');
  });

  test('renders variable name and value in chips', () => {
    const c = mockContainer();
    const v = new VariableInspector(c, THEME);
    v.update(fakeStep(ACTIONS.SEARCH_COMPARE_KEY, { variables: { key: 42 } }));
    ok(c.innerHTML.includes('key'), 'chip should show variable name');
    ok(c.innerHTML.includes('42'),  'chip should show variable value');
  });

  test('resolves node ID to key array', () => {
    const c    = mockContainer();
    const v    = new VariableInspector(c, THEME);
    const step = fakeStep(ACTIONS.SEARCH_ENTER_NODE, {
      variables: { node: 'n1' },
    });
    v.update(step);
    // n1 has keys [20], so it should display [20]
    ok(c.innerHTML.includes('[20]'), 'node ID should resolve to key array');
    ok(!c.innerHTML.includes('n1'), 'raw node ID should not appear');
  });

  test('resolves node_123 style IDs too', () => {
    const c    = mockContainer();
    const v    = new VariableInspector(c, THEME);
    const step = {
      ...fakeStep(ACTIONS.SEARCH_ENTER_NODE),
      variables: { node: 'node_1' },
      state: {
        ...fakeState(),
        nodes: { node_1: { id: 'node_1', keys: [5, 10], children: [], isLeaf: true, parentId: null } },
      },
    };
    v.update(step);
    ok(c.innerHTML.includes('[5, 10]'), 'node_N ID should resolve to key array');
  });

  test('handles missing node ID gracefully (no throw)', () => {
    const c    = mockContainer();
    const v    = new VariableInspector(c, THEME);
    const step = fakeStep(ACTIONS.SEARCH_ENTER_NODE, {
      variables: { node: 'n_nonexistent' },
    });
    v.update(step);
    ok(true, 'should not throw for missing node ID');
  });

  test('non-node-ID string values are rendered as-is', () => {
    const c = mockContainer();
    const v = new VariableInspector(c, THEME);
    v.update(fakeStep(ACTIONS.SEARCH_COMPARE_KEY, {
      variables: { key: 'hello' },
    }));
    ok(c.innerHTML.includes('hello'));
  });

  test('numeric values are rendered correctly', () => {
    const c = mockContainer();
    const v = new VariableInspector(c, THEME);
    v.update(fakeStep(ACTIONS.SEARCH_COMPARE_KEY, {
      variables: { depth: 3, keyIndex: 1 },
    }));
    ok(c.innerHTML.includes('depth'));
    ok(c.innerHTML.includes('3'));
    ok(c.innerHTML.includes('keyIndex'));
  });

  test('t variable is suppressed from display', () => {
    const c = mockContainer();
    const v = new VariableInspector(c, THEME);
    v.update(fakeStep(ACTIONS.SEARCH_ENTER_NODE, {
      variables: { t: 2, key: 10 },
    }));
    // t should be suppressed, key should show
    ok(c.innerHTML.includes('key'), 'key should appear');
    // t should not appear as a chip label (it might appear in values though)
    const chipT = c.innerHTML.indexOf('>t<');
    ok(chipT === -1, 't variable should be suppressed');
  });

  test('destroy() empties container', () => {
    const c = mockContainer();
    const v = new VariableInspector(c, THEME);
    v.destroy();
    eq(c.innerHTML, '');
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Section 1d --, InvariantTracker
// ─────────────────────────────────────────────────────────────────────────────

suite('InvariantTracker --, invariant checking', () => {
  const { InvariantTracker } = require('../narrative/InvariantTracker');

  test('constructs without throwing', () => {
    const c = mockContainer();
    new InvariantTracker(c, THEME);
    ok(true);
  });

  test('initial render shows empty state message', () => {
    const c = mockContainer();
    new InvariantTracker(c, THEME);
    ok(c.innerHTML.includes('Run an operation'), 'should show empty state message');
  });

  test('update() shows t, min/max keys', () => {
    const c = mockContainer();
    const t = new InvariantTracker(c, THEME);
    t.update(fakeStep(ACTIONS.INITIAL_STATE));
    ok(c.innerHTML.includes('2'), 't=2 should appear');
    ok(c.innerHTML.includes('3'), '2t-1=3 for t=2 should appear');
    ok(c.innerHTML.includes('1'), 't-1=1 should appear');
  });

  test('shows tree height, total nodes, total keys', () => {
    const c = mockContainer();
    const t = new InvariantTracker(c, THEME);
    t.update(fakeStep(ACTIONS.INITIAL_STATE));
    const html = c.innerHTML;
    ok(html.includes('2') || html.includes('Tree height'), 'should show tree height');
    ok(html.includes('3') || html.includes('Total nodes'), 'should show total nodes (n1+n2+n3=3)');
  });

  test('shows active node section when active node is highlighted', () => {
    const c = mockContainer();
    const t = new InvariantTracker(c, THEME);
    t.update(fakeStep(ACTIONS.SEARCH_ENTER_NODE, {
      highlights: { nodes: [{ nodeId: 'n2', role: NODE_ROLES.ACTIVE }], keys: [], edges: [] },
    }));
    ok(c.innerHTML.includes('n2'), 'active node ID should appear in tracker');
    ok(c.innerHTML.includes('ACTIVE NODE'), 'active node section should appear');
  });

  test('no active node section when no highlight', () => {
    const c = mockContainer();
    const t = new InvariantTracker(c, THEME);
    t.update(fakeStep(ACTIONS.INITIAL_STATE, {
      highlights: { nodes: [], keys: [], edges: [] },
    }));
    ok(!c.innerHTML.includes('ACTIVE NODE'), 'no active node section when nothing highlighted');
  });

  test('FULL badge appears when node has 2t-1 keys', () => {
    const c = mockContainer();
    const t = new InvariantTracker(c, THEME);
    // n3 has 2 keys; 2t-1=3 for t=2, so 3 keys = FULL. Build a full node.
    const state = fakeState({
      nodes: {
        n1: { id: 'n1', keys: [10, 20], children: [], isLeaf: true, parentId: null },
      },
    });
    state.rootId = 'n1';
    const step = {
      ...fakeStep(ACTIONS.SEARCH_ENTER_NODE),
      state,
      highlights: { nodes: [{ nodeId: 'n1', role: NODE_ROLES.ACTIVE }], keys: [], edges: [] },
    };
    t.update(step);
    // n1 now has 2 keys; for t=2, max=3, so NOT full yet
    // Let's build a node with exactly 3 keys
    state.nodes.n1.keys = [10, 20, 30];
    t.update({ ...step, state });
    ok(c.innerHTML.includes('FULL'), 'FULL badge should appear at 2t-1 keys');
  });

  test('OVERFLOW badge appears for overflow step', () => {
    const c = mockContainer();
    const t = new InvariantTracker(c, THEME);
    const state = fakeState({
      nodes: {
        n1: { id: 'n1', keys: [10, 20, 30, 40], children: [], isLeaf: true, parentId: null },
      },
    });
    state.rootId = 'n1';
    const step = {
      ...fakeStep(ACTIONS.OVERFLOW_DETECTED),
      state,
      highlights: { nodes: [{ nodeId: 'n1', role: NODE_ROLES.OVERFLOW }], keys: [], edges: [] },
    };
    t.update(step);
    ok(c.innerHTML.includes('OVERFLOW'), 'OVERFLOW badge should appear at >2t-1 keys');
  });

  test('invariant check marks: sorted check passes for correctly sorted node', () => {
    const c = mockContainer();
    const t = new InvariantTracker(c, THEME);
    t.update(fakeStep(ACTIONS.INITIAL_STATE)); // uses default fakeState which is sorted
    // The ✓ symbol should appear (sorted invariant passes)
    ok(c.innerHTML.includes('✓'), 'sorted invariant should be marked passing');
  });

  test('update() with every action does not throw', () => {
    for (const action of Object.values(ACTIONS)) {
      const c = mockContainer();
      const t = new InvariantTracker(c, THEME);
      t.update(fakeStep(action));
      ok(true, `InvariantTracker should not throw for action ${action}`);
    }
  });

  test('destroy() empties container', () => {
    const c = mockContainer();
    const t = new InvariantTracker(c, THEME);
    t.destroy();
    eq(c.innerHTML, '');
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Section 1e --, ComplexityPanel
// ─────────────────────────────────────────────────────────────────────────────

suite('ComplexityPanel --, complexity display', () => {
  const { ComplexityPanel, COMPLEXITY } = require('../narrative/ComplexityPanel');

  test('COMPLEXITY has entries for all three operations', () => {
    ok(COMPLEXITY.search?.time, 'search should have time complexity');
    ok(COMPLEXITY.insert?.time, 'insert should have time complexity');
    ok(COMPLEXITY.delete?.time, 'delete should have time complexity');
  });

  test('all operations have O(... log ...) in time complexity', () => {
    for (const op of ['search', 'insert', 'delete']) {
      ok(COMPLEXITY[op].time.includes('log'), `${op} time should include log`);
    }
  });

  test('constructs without throwing', () => {
    const c = mockContainer();
    new ComplexityPanel(c, THEME);
    ok(true);
  });

  test('no op loaded: shows placeholder', () => {
    const c = mockContainer();
    const p = new ComplexityPanel(c, THEME);
    ok(c.innerHTML.includes('Select an operation'), 'placeholder before loadOperation');
  });

  test('loadOperation shows time and space', () => {
    const c = mockContainer();
    const p = new ComplexityPanel(c, THEME);
    p.loadOperation('search');
    ok(c.innerHTML.includes('Time'), 'time label should appear');
    ok(c.innerHTML.includes('Space'), 'space label should appear');
  });

  test('loadOperation("insert") shows insert complexity', () => {
    const c = mockContainer();
    const p = new ComplexityPanel(c, THEME);
    p.loadOperation('insert');
    ok(c.innerHTML.includes('log'), 'complexity should include log');
  });

  test('update() with BORROW_LEFT_ROTATE shows borrow case', () => {
    const c = mockContainer();
    const p = new ComplexityPanel(c, THEME);
    p.loadOperation('delete');
    p.update(fakeStep(ACTIONS.BORROW_LEFT_ROTATE, { meta: { phase: 'unwind', reason: 'rotate', depth: 1 } }));
    ok(c.innerHTML.includes('Borrow') || c.innerHTML.includes('CURRENT CASE'),
      'borrow case should appear');
  });

  test('update() with SEARCH_FOUND shows found case', () => {
    const c = mockContainer();
    const p = new ComplexityPanel(c, THEME);
    p.loadOperation('search');
    p.update(fakeStep(ACTIONS.SEARCH_FOUND, { meta: { phase: 'act', reason: 'found', depth: 1 } }));
    ok(c.innerHTML.includes('found') || c.innerHTML.includes('CURRENT CASE'),
      'found case should be highlighted');
  });

  test('update() with no matching case still renders without throwing', () => {
    const c = mockContainer();
    const p = new ComplexityPanel(c, THEME);
    p.loadOperation('search');
    p.update(fakeStep(ACTIONS.SEARCH_ENTER_NODE, { meta: { phase: 'descend', depth: 0 } }));
    ok(true);
  });

  test('destroy() empties container', () => {
    const c = mockContainer();
    const p = new ComplexityPanel(c, THEME);
    p.destroy();
    eq(c.innerHTML, '');
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Section 1f --, RecursionDepth
// ─────────────────────────────────────────────────────────────────────────────

suite('RecursionDepth --, breadcrumb trail', () => {
  const { RecursionDepth } = require('../narrative/RecursionDepth');

  test('constructs without throwing', () => {
    const c = mockContainer();
    new RecursionDepth(c, THEME);
    ok(true);
  });

  test('initial render shows dash placeholder', () => {
    const c = mockContainer();
    new RecursionDepth(c, THEME);
    ok(c.innerHTML.includes('--,') || c.innerHTML.includes('&mdash;') || c.innerHTML.length > 0);
  });

  test('update() with descend phase adds a breadcrumb', () => {
    const c = mockContainer();
    const r = new RecursionDepth(c, THEME);
    r.update(fakeStep(ACTIONS.SEARCH_ENTER_NODE, {
      highlights: { nodes: [{ nodeId: 'n1', role: NODE_ROLES.ACTIVE }], keys: [], edges: [] },
      meta: { phase: 'descend', depth: 0 },
    }));
    ok(c.innerHTML.includes('n1'), 'n1 should appear in the breadcrumb');
  });

  test('descending twice adds two breadcrumbs', () => {
    const c = mockContainer();
    const r = new RecursionDepth(c, THEME);
    r.update(fakeStep(ACTIONS.SEARCH_ENTER_NODE, {
      highlights: { nodes: [{ nodeId: 'n1', role: NODE_ROLES.ACTIVE }], keys: [], edges: [] },
      meta: { phase: 'descend', depth: 0 },
    }));
    r.update(fakeStep(ACTIONS.SEARCH_ENTER_NODE, {
      highlights: { nodes: [{ nodeId: 'n2', role: NODE_ROLES.ACTIVE }], keys: [], edges: [] },
      meta: { phase: 'descend', depth: 1 },
    }));
    ok(c.innerHTML.includes('n1'), 'n1 should still be in trail');
    ok(c.innerHTML.includes('n2'), 'n2 should be added to trail');
  });

  test('unwind phase trims the trail', () => {
    const c = mockContainer();
    const r = new RecursionDepth(c, THEME);
    // descend to depth 2
    r.update(fakeStep(ACTIONS.SEARCH_ENTER_NODE, {
      highlights: { nodes: [{ nodeId: 'n1', role: NODE_ROLES.ACTIVE }], keys: [], edges: [] },
      meta: { phase: 'descend', depth: 0 },
    }));
    r.update(fakeStep(ACTIONS.SEARCH_ENTER_NODE, {
      highlights: { nodes: [{ nodeId: 'n2', role: NODE_ROLES.ACTIVE }], keys: [], edges: [] },
      meta: { phase: 'descend', depth: 1 },
    }));
    eq(r._trail.length, 2);

    // unwind to depth 0 --, trail should shrink
    r.update(fakeStep(ACTIONS.SEARCH_NOT_FOUND, {
      highlights: { nodes: [], keys: [], edges: [] },
      meta: { phase: 'unwind', depth: 0 },
    }));
    ok(r._trail.length < 2, `Trail should shrink on unwind, got ${r._trail.length}`);
  });

  test('loadOperation() resets the trail', () => {
    const c = mockContainer();
    const r = new RecursionDepth(c, THEME);
    r.update(fakeStep(ACTIONS.SEARCH_ENTER_NODE, {
      highlights: { nodes: [{ nodeId: 'n1', role: NODE_ROLES.ACTIVE }], keys: [], edges: [] },
      meta: { phase: 'descend', depth: 0 },
    }));
    eq(r._trail.length, 1);
    r.loadOperation();
    eq(r._trail.length, 0);
  });

  test('update() with every action does not throw', () => {
    for (const action of Object.values(ACTIONS)) {
      const c = mockContainer();
      const r = new RecursionDepth(c, THEME);
      r.update(fakeStep(action));
      ok(true);
    }
  });

  test('destroy() empties container', () => {
    const c = mockContainer();
    const r = new RecursionDepth(c, THEME);
    r.destroy();
    eq(c.innerHTML, '');
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Section 1g --, NarrativeLayer orchestration (no DOM)
// ─────────────────────────────────────────────────────────────────────────────

suite('NarrativeLayer --, orchestration', () => {
  // NarrativeLayer needs querySelector to find sub-panel divs --, build a
  // richer mock that supports it.
  function mockNarrContainer() {
    const divs = {};
    let _html  = '';
    return {
      get innerHTML() { return _html; },
      set innerHTML(v) {
        _html = v;
        // After innerHTML is set by _buildLayout, create mock child divs
        const idRe = /id="([^"]+)"/g;
        let m;
        while ((m = idRe.exec(v)) !== null) {
          if (!divs[m[1]]) divs[m[1]] = mockContainer();
        }
      },
      querySelector(sel) {
        const idMatch = sel.match(/^#(.+)/);
        if (idMatch) return divs[idMatch[1]] ?? mockContainer();
        return mockContainer();
      },
      style: { cssText: '' },
    };
  }

  test('NarrativeLayer constructs without throwing', () => {
    const c = mockNarrContainer();
    const n = new (require('../narrative/NarrativeLayer').NarrativeLayer)(c);
    ok(n !== null);
    n.destroy();
  });

  test('loadOperation("search") does not throw', () => {
    const c = mockNarrContainer();
    const n = new (require('../narrative/NarrativeLayer').NarrativeLayer)(c);
    n.loadOperation('search');
    ok(true);
    n.destroy();
  });

  test('loadOperation() with all three ops does not throw', () => {
    for (const op of ['search', 'insert', 'delete']) {
      const c = mockNarrContainer();
      const n = new (require('../narrative/NarrativeLayer').NarrativeLayer)(c);
      n.loadOperation(op);
      ok(true, `loadOperation(${op}) should not throw`);
      n.destroy();
    }
  });

  test('update() with every action does not throw', () => {
    const { NarrativeLayer } = require('../narrative/NarrativeLayer');
    const c = mockNarrContainer();
    const n = new NarrativeLayer(c);
    n.loadOperation('search');
    for (const action of Object.values(ACTIONS)) {
      n.update(fakeStep(action), null);
      ok(true, `NarrativeLayer.update() should not throw for ${action}`);
    }
    n.destroy();
  });

  test('panels getter exposes all six sub-panels', () => {
    const { NarrativeLayer } = require('../narrative/NarrativeLayer');
    const c = mockNarrContainer();
    const n = new NarrativeLayer(c);
    const p = n.panels;
    ok(p.invariant   !== undefined, 'invariant panel should be accessible');
    ok(p.recursion   !== undefined, 'recursion panel should be accessible');
    ok(p.pseudocode  !== undefined, 'pseudocode panel should be accessible');
    ok(p.explanation !== undefined, 'explanation panel should be accessible');
    ok(p.variables   !== undefined, 'variables panel should be accessible');
    ok(p.complexity  !== undefined, 'complexity panel should be accessible');
    n.destroy();
  });

  test('destroy() does not throw', () => {
    const { NarrativeLayer } = require('../narrative/NarrativeLayer');
    const c = mockNarrContainer();
    const n = new NarrativeLayer(c);
    n.destroy();
    ok(true);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Section 2 --, jsdom integration tests
// ─────────────────────────────────────────────────────────────────────────────

let jsdomAvail = false;
try { require('jsdom'); jsdomAvail = true; } catch (_) {}

if (!jsdomAvail) {
  console.log('\nSkipping jsdom tests --, run: npm install jsdom\n');
} else {
  const { JSDOM } = require('jsdom');

  function makeDoc() {
    const dom = new JSDOM('<!DOCTYPE html><body><div id="root"></div></body>');
    return dom.window.document;
  }

  suite('NarrativeLayer --, real DOM (jsdom)', () => {
    const { NarrativeLayer } = require('../narrative/NarrativeLayer');

    test('builds section divs for all six panels', () => {
      const doc  = makeDoc();
      const root = doc.getElementById('root');
      const n    = new NarrativeLayer(root);

      ok(root.querySelector('#narr-invariant')   !== null, 'invariant div');
      ok(root.querySelector('#narr-recursion')   !== null, 'recursion div');
      ok(root.querySelector('#narr-pseudocode')  !== null, 'pseudocode div');
      ok(root.querySelector('#narr-explanation') !== null, 'explanation div');
      ok(root.querySelector('#narr-variables')   !== null, 'variables div');
      ok(root.querySelector('#narr-complexity')  !== null, 'complexity div');
      n.destroy();
    });

    test('explanation section contains text after update()', () => {
      const doc  = makeDoc();
      const root = doc.getElementById('root');
      const n    = new NarrativeLayer(root);

      n.loadOperation('search');
      n.update(fakeStep(ACTIONS.SEARCH_FOUND, { explanation: 'Unique test string 99999.' }), null);

      const el = root.querySelector('#narr-explanation');
      ok(el?.innerHTML?.includes('99999'), 'explanation text should appear in DOM');
      n.destroy();
    });

    test('KEY STEP badge appears in DOM for isKeyStep=true', () => {
      const doc  = makeDoc();
      const root = doc.getElementById('root');
      const n    = new NarrativeLayer(root);

      n.loadOperation('insert');
      n.update(fakeStep(ACTIONS.INSERT_INTO_LEAF, { isKeyStep: true }), null);

      const el = root.querySelector('#narr-explanation');
      ok(el?.innerHTML?.includes('KEY STEP'), 'KEY STEP badge should be in DOM');
      n.destroy();
    });

    test('pseudocode section has content after loadOperation("insert")', () => {
      const doc  = makeDoc();
      const root = doc.getElementById('root');
      const n    = new NarrativeLayer(root);

      n.loadOperation('insert');

      const el = root.querySelector('#narr-pseudocode');
      ok((el?.innerHTML?.length ?? 0) > 50,
        'pseudocode section should have substantial content after loadOperation');
      n.destroy();
    });

    test('invariant tracker shows B-TREE PROPERTIES header after update()', () => {
      const doc  = makeDoc();
      const root = doc.getElementById('root');
      const n    = new NarrativeLayer(root);

      n.loadOperation('search');
      n.update(fakeStep(ACTIONS.INITIAL_STATE), null);

      const el = root.querySelector('#narr-invariant');
      ok(el?.innerHTML?.includes('B-TREE PROPERTIES') || el?.innerHTML?.includes('PROPERTIES'),
        'invariant tracker should show properties header');
      n.destroy();
    });

    test('variable inspector shows key variable chip', () => {
      const doc  = makeDoc();
      const root = doc.getElementById('root');
      const n    = new NarrativeLayer(root);

      n.loadOperation('search');
      n.update(fakeStep(ACTIONS.SEARCH_COMPARE_KEY, {
        variables: { key: 42, depth: 0 },
      }), null);

      const el = root.querySelector('#narr-variables');
      ok(el?.innerHTML?.includes('42'), 'key value 42 should appear in variable inspector');
      n.destroy();
    });

    test('complexity section appears after loadOperation("delete")', () => {
      const doc  = makeDoc();
      const root = doc.getElementById('root');
      const n    = new NarrativeLayer(root);

      n.loadOperation('delete');

      const el = root.querySelector('#narr-complexity');
      ok(el?.innerHTML?.includes('log') || el?.innerHTML?.includes('Delete'),
        'complexity section should have delete complexity info');
      n.destroy();
    });

    test('destroy() empties the root container', () => {
      const doc  = makeDoc();
      const root = doc.getElementById('root');
      const n    = new NarrativeLayer(root);

      n.loadOperation('search');
      n.update(fakeStep(ACTIONS.INITIAL_STATE), null);
      n.destroy();

      eq(root.innerHTML, '');
    });

    test('update() with all ACTIONS on all three ops does not throw', () => {
      const doc  = makeDoc();
      const root = doc.getElementById('root');
      const n    = new NarrativeLayer(root);
      let errors = 0;

      for (const op of ['search', 'insert', 'delete']) {
        n.loadOperation(op);
        for (const action of Object.values(ACTIONS)) {
          try { n.update(fakeStep(action), null); }
          catch (e) { errors++; console.error(`${op}/${action}:`, e.message); }
        }
      }
      eq(errors, 0, 'No errors updating NarrativeLayer with any operation/action combo');
      n.destroy();
    });
  });
}

// ─────────────────────────────────────────────────────────────────────────────

summary();
process.exit(0);