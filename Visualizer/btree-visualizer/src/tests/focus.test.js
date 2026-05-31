// Stage 6 Tests --, FocusController
//
// Two sections:
//   1. Pure-Node tests  --, mock d3, no DOM. Verifies rule logic: which nodes get
//      dimmed, which stay full, how restoreAll behaves, INITIAL_STATE handling.
//   2. jsdom tests      --, real DOM via AnimationLayer. Reads computed opacity
//      values off DOM elements after render() to verify focus rules end-to-end.
//
// Run:
//   node src/tests/focus.test.js
//
// For section 2:
//   npm install jsdom d3

'use strict';

const { test, suite, summary, eq, ok } = require('./runner');
const { ACTIONS, NODE_ROLES }           = require('../core/constants');
const { createTheme }                   = require('../animation/ThemeModule');

const THEME = createTheme();

// ─── Fixtures ─────────────────────────────────────────────────────────────────

function fakeStep(action, nodeHighlights = [], overrides = {}) {
  return {
    stepIndex: 0,
    action,
    isKeyStep: false,
    state: {
      t: 2,
      rootId: 'n1',
      nodes: {
        n1: { id: 'n1', keys: [20],     children: ['n2', 'n3'], isLeaf: false, parentId: null },
        n2: { id: 'n2', keys: [10],     children: [],           isLeaf: true,  parentId: 'n1' },
        n3: { id: 'n3', keys: [30, 40], children: [],           isLeaf: true,  parentId: 'n1' },
      },
    },
    highlights:     { nodes: nodeHighlights, keys: [], edges: [] },
    explanation:    'test',
    pseudocodeLine: 0,
    variables:      { t: 2 },
    meta:           { phase: 'descend', depth: 0 },
    ...overrides,
  };
}

// A fake plan where everything is zero so focus transitions fire synchronously
function zeroPlan() {
  return {
    nodeEnter: { delay: 0, duration: 0 }, nodeExit:  { delay: 0, duration: 0 },
    nodeMove:  { delay: 0, duration: 0 }, nodeResize:{ delay: 0, duration: 0 },
    keyEnter:  { delay: 0, duration: 0 }, keyExit:   { delay: 0, duration: 0 },
    keyMove:   { delay: 0, duration: 0 }, edgeEnter: { delay: 0, duration: 0 },
    edgeExit:  { delay: 0, duration: 0 }, edgeReroute:{ delay: 0, duration: 0 },
    highlightFade: { delay: 0, duration: 0 },
    focusChange:   { delay: 0, duration: 0 },
    cameraPan:     { delay: 0, duration: 0 },
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Section 1 --, Pure-Node tests using a mock d3 layer
// ─────────────────────────────────────────────────────────────────────────────

// Builds a mock nodes-layer with a known set of node-group elements.
// Each element tracks what opacity it was last given.
function makeMockLayer(nodeIds) {
  const opacities = {};
  for (const id of nodeIds) opacities[id] = 1.0;

  // Build minimal d3-like mock: selectAll returns elements with the right data
  const mockD3 = {
    select: (el) => ({
      transition: () => ({ delay: () => ({ duration: () => ({ attr: () => {} }) }) }),
      attr: (name, val) => { /* not needed */ },
    }),
  };

  // We'll track calls via the selection object directly
  const mockLayer = {
    _opacities: opacities,
    selectAll(selector) {
      if (selector !== 'g.node-group') return { each: () => {}, attr: () => {} };

      return {
        // .each(fn) is what FocusController calls --, simulate it with our node data
        each(fn) {
          for (const id of nodeIds) {
            // Build a minimal element-like object that can be d3.select()'d
            const el = { _nodeId: id, _layer: mockLayer };
            fn.call(el, id);
          }
        },
        // .attr() for restoreAll --, sets all at once
        attr(name, val) {
          if (name === 'opacity') {
            for (const id of nodeIds) opacities[id] = val;
          }
          return this;
        },
        transition() {
          return {
            duration: () => ({
              attr: (name, val) => {
                if (name === 'opacity') {
                  for (const id of nodeIds) opacities[id] = val;
                }
              },
            }),
          };
        },
      };
    },
  };

  // The d3.select(domElement) call inside .each() needs to return something
  // that can set opacity. We build a special d3 that tracks per-node opacity.
  const trackingD3 = {
    select(el) {
      const nodeId = el._nodeId;
      return {
        attr(name, val) {
          if (name === 'opacity' && nodeId) opacities[nodeId] = val;
          return this;
        },
        transition() {
          return {
            delay:    () => this,
            duration: () => this,
            attr(name, val) {
              if (name === 'opacity' && nodeId) opacities[nodeId] = val;
              return this;
            },
          };
        },
      };
    },
  };

  return { mockLayer, trackingD3, opacities };
}

function makeFocusController(nodeIds) {
  const { FocusController } = require('../animation/FocusController');
  const { mockLayer, trackingD3, opacities } = makeMockLayer(nodeIds);
  const ctrl = new FocusController(mockLayer, THEME, trackingD3);
  return { ctrl, opacities };
}

suite('FocusController --, RESTORE_ALL actions', () => {
  test('INITIAL_STATE restores all nodes to opacity 1.0', () => {
    const { ctrl, opacities } = makeFocusController(['n1', 'n2', 'n3']);
    // Pre-dim everything by hand
    opacities.n2 = 0.25;
    opacities.n3 = 0.25;

    ctrl.update(fakeStep(ACTIONS.INITIAL_STATE, []), zeroPlan());
    eq(opacities.n1, 1.0);
    eq(opacities.n2, 1.0);
    eq(opacities.n3, 1.0);
  });

  test('OPERATION_COMPLETE restores all nodes to opacity 1.0', () => {
    const { ctrl, opacities } = makeFocusController(['n1', 'n2', 'n3']);
    opacities.n1 = 0.25;
    opacities.n2 = 0.25;
    opacities.n3 = 0.25;

    ctrl.update(fakeStep(ACTIONS.OPERATION_COMPLETE, []), zeroPlan());
    eq(opacities.n1, 1.0);
    eq(opacities.n2, 1.0);
    eq(opacities.n3, 1.0);
  });
});

suite('FocusController --, dimming logic', () => {
  test('a highlighted node stays at full opacity', () => {
    const { ctrl, opacities } = makeFocusController(['n1', 'n2', 'n3']);
    ctrl.update(
      fakeStep(ACTIONS.SEARCH_ENTER_NODE, [{ nodeId: 'n2', role: NODE_ROLES.ACTIVE }]),
      zeroPlan()
    );
    eq(opacities.n2, 1.0);
  });

  test('a non-highlighted, non-root node is dimmed to 0.25', () => {
    const { ctrl, opacities } = makeFocusController(['n1', 'n2', 'n3']);
    ctrl.update(
      fakeStep(ACTIONS.SEARCH_ENTER_NODE, [{ nodeId: 'n2', role: NODE_ROLES.ACTIVE }]),
      zeroPlan()
    );
    // n3 is neither highlighted nor root --, should be dimmed
    eq(opacities.n3, 0.25);
  });

  test('root node is never dimmed even when not highlighted', () => {
    const { ctrl, opacities } = makeFocusController(['n1', 'n2', 'n3']);
    // Highlight only n2, leaving root (n1) out of highlights
    ctrl.update(
      fakeStep(ACTIONS.SEARCH_ENTER_NODE, [{ nodeId: 'n2', role: NODE_ROLES.ACTIVE }]),
      zeroPlan()
    );
    // n1 is root --, should stay at 1.0
    eq(opacities.n1, 1.0);
  });

  test('multiple highlighted nodes all stay full', () => {
    const { ctrl, opacities } = makeFocusController(['n1', 'n2', 'n3']);
    ctrl.update(
      fakeStep(ACTIONS.SPLIT_EXECUTE, [
        { nodeId: 'n1', role: NODE_ROLES.PARENT },
        { nodeId: 'n2', role: NODE_ROLES.SPLIT_LEFT },
        { nodeId: 'n3', role: NODE_ROLES.SPLIT_RIGHT },
      ]),
      zeroPlan()
    );
    eq(opacities.n1, 1.0);
    eq(opacities.n2, 1.0);
    eq(opacities.n3, 1.0);
  });

  test('with no highlights, only root stays full --, all others dimmed', () => {
    const { ctrl, opacities } = makeFocusController(['n1', 'n2', 'n3']);
    ctrl.update(fakeStep(ACTIONS.SEARCH_COMPARE_KEY, []), zeroPlan());
    eq(opacities.n1, 1.0);   // root always full
    eq(opacities.n2, 0.25);
    eq(opacities.n3, 0.25);
  });

  test('calling update() twice correctly re-focuses for the new step', () => {
    const { ctrl, opacities } = makeFocusController(['n1', 'n2', 'n3']);

    // Step 1: n2 is active
    ctrl.update(
      fakeStep(ACTIONS.SEARCH_ENTER_NODE, [{ nodeId: 'n2', role: NODE_ROLES.ACTIVE }]),
      zeroPlan()
    );
    eq(opacities.n2, 1.0);
    eq(opacities.n3, 0.25);

    // Step 2: n3 is now active instead
    ctrl.update(
      fakeStep(ACTIONS.SEARCH_ENTER_NODE, [{ nodeId: 'n3', role: NODE_ROLES.ACTIVE }]),
      zeroPlan()
    );
    eq(opacities.n3, 1.0);
    eq(opacities.n2, 0.25);
  });

  test('underflow-highlighted node is not dimmed', () => {
    const { ctrl, opacities } = makeFocusController(['n1', 'n2', 'n3']);
    ctrl.update(
      fakeStep(ACTIONS.UNDERFLOW_DETECTED, [
        { nodeId: 'n2', role: NODE_ROLES.UNDERFLOW },
        { nodeId: 'n1', role: NODE_ROLES.PARENT },
      ]),
      zeroPlan()
    );
    eq(opacities.n2, 1.0);
    eq(opacities.n1, 1.0);
    eq(opacities.n3, 0.25);
  });

  test('dim role in highlights still keeps the node at full opacity', () => {
    // Even a "dim" highlight means the node is referenced in this step
    const { ctrl, opacities } = makeFocusController(['n1', 'n2', 'n3']);
    ctrl.update(
      fakeStep(ACTIONS.SEARCH_ENTER_NODE, [
        { nodeId: 'n2', role: NODE_ROLES.ACTIVE },
        { nodeId: 'n3', role: NODE_ROLES.DIM },
      ]),
      zeroPlan()
    );
    // n3 is in highlights (even as dim role), so FocusController leaves its opacity
    // at 1.0 --, the dim styling is NodeRenderer's job, not ours
    eq(opacities.n3, 1.0);
  });

  test('update() with null plan does not throw', () => {
    const { ctrl } = makeFocusController(['n1', 'n2', 'n3']);
    ctrl.update(fakeStep(ACTIONS.SEARCH_ENTER_NODE, []), null);
    ok(true);
  });

  test('update() with missing state.rootId does not throw', () => {
    const { ctrl } = makeFocusController(['n1', 'n2', 'n3']);
    const step = fakeStep(ACTIONS.SEARCH_ENTER_NODE, []);
    delete step.state.rootId;
    ctrl.update(step, zeroPlan());
    ok(true);
  });
});

suite('FocusController --, restoreAll()', () => {
  test('restoreAll() synchronously sets all nodes to opacity 1.0', () => {
    const { ctrl, opacities } = makeFocusController(['n1', 'n2', 'n3']);
    opacities.n2 = 0.25;
    opacities.n3 = 0.25;

    ctrl.restoreAll(0);
    eq(opacities.n1, 1.0);
    eq(opacities.n2, 1.0);
    eq(opacities.n3, 1.0);
  });

  test('restoreAll() with duration > 0 does not throw', () => {
    const { ctrl } = makeFocusController(['n1', 'n2', 'n3']);
    ctrl.restoreAll(300);
    ok(true);
  });

  test('restoreAll() called with no args (default 0) does not throw', () => {
    const { ctrl } = makeFocusController(['n1']);
    ctrl.restoreAll();
    ok(true);
  });
});

suite('FocusController --, destroy()', () => {
  test('destroy() sets _layer to null', () => {
    const { ctrl } = makeFocusController(['n1']);
    ctrl.destroy();
    eq(ctrl._layer, null);
  });

  test('destroy() does not throw', () => {
    const { ctrl } = makeFocusController(['n1', 'n2', 'n3']);
    ctrl.destroy();
    ok(true);
  });
});

suite('FocusController --, search sequence', () => {
  test('SEARCH_COMPARE_KEY dims non-active, non-root nodes', () => {
    const { ctrl, opacities } = makeFocusController(['n1', 'n2', 'n3']);
    ctrl.update(
      fakeStep(ACTIONS.SEARCH_COMPARE_KEY, [{ nodeId: 'n2', role: NODE_ROLES.ACTIVE }]),
      zeroPlan()
    );
    eq(opacities.n2, 1.0);
    eq(opacities.n3, 0.25);
    eq(opacities.n1, 1.0); // root always full
  });

  test('SEARCH_FOUND keeps found node at full opacity', () => {
    const { ctrl, opacities } = makeFocusController(['n1', 'n2', 'n3']);
    ctrl.update(
      fakeStep(ACTIONS.SEARCH_FOUND, [{ nodeId: 'n3', role: NODE_ROLES.ACTIVE }]),
      zeroPlan()
    );
    eq(opacities.n3, 1.0);
    eq(opacities.n2, 0.25);
  });

  test('SEARCH_NOT_FOUND followed by OPERATION_COMPLETE restores all', () => {
    const { ctrl, opacities } = makeFocusController(['n1', 'n2', 'n3']);
    ctrl.update(
      fakeStep(ACTIONS.SEARCH_NOT_FOUND, [{ nodeId: 'n2', role: NODE_ROLES.ACTIVE }]),
      zeroPlan()
    );
    // n3 is dimmed after not-found step
    eq(opacities.n3, 0.25);

    // Operation complete should restore everything
    ctrl.update(fakeStep(ACTIONS.OPERATION_COMPLETE, []), zeroPlan());
    eq(opacities.n3, 1.0);
  });
});

suite('FocusController --, merge and borrow sequences', () => {
  test('MERGE_PREPARE dims nodes not in the merge group', () => {
    // Extend to a 4-node tree
    const { ctrl, opacities } = makeFocusController(['n1', 'n2', 'n3', 'n4']);
    ctrl.update(
      fakeStep(ACTIONS.MERGE_PREPARE, [
        { nodeId: 'n1', role: NODE_ROLES.PARENT },
        { nodeId: 'n2', role: NODE_ROLES.MERGE_TARGET },
        { nodeId: 'n3', role: NODE_ROLES.MERGE_SOURCE },
      ]),
      zeroPlan()
    );
    eq(opacities.n1, 1.0);
    eq(opacities.n2, 1.0);
    eq(opacities.n3, 1.0);
    eq(opacities.n4, 0.25);
  });

  test('BORROW_LEFT_ROTATE: sibling, parent, active all stay full', () => {
    const { ctrl, opacities } = makeFocusController(['n1', 'n2', 'n3', 'n4']);
    ctrl.update(
      fakeStep(ACTIONS.BORROW_LEFT_ROTATE, [
        { nodeId: 'n1', role: NODE_ROLES.PARENT },
        { nodeId: 'n2', role: NODE_ROLES.SIBLING_LEFT },
        { nodeId: 'n3', role: NODE_ROLES.ACTIVE },
      ]),
      zeroPlan()
    );
    eq(opacities.n1, 1.0);
    eq(opacities.n2, 1.0);
    eq(opacities.n3, 1.0);
    eq(opacities.n4, 0.25);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Section 2 --, jsdom + d3 integration tests
// ─────────────────────────────────────────────────────────────────────────────

let jsdomAvail = false;
let d3Avail    = false;
try { require('jsdom'); jsdomAvail = true; } catch (_) {}
try { require('d3');    d3Avail    = true; } catch (_) {}

if (!jsdomAvail || !d3Avail) {
  console.log('\nSkipping DOM tests --, run: npm install jsdom d3\n');
} else {
  const { JSDOM } = require('jsdom');

  const _base = new JSDOM('<!DOCTYPE html><body></body>', { url: 'http://localhost' });
  global.window   = _base.window;
  global.document = _base.window.document;
  global.location = _base.window.location;
  global.SVGElement = _base.window.SVGElement;
  try {
    global.navigator = _base.window.navigator;
  } catch (_) {
    Object.defineProperty(global, 'navigator', {
      value: _base.window.navigator, configurable: true, writable: true,
    });
  }

  const d3 = require('d3');
  const { AnimationLayer } = require('../animation/AnimationLayer');
  const { resetIdCounter } = require('../core/shared');
  const { createTree }     = require('../core/BTree');
  const { insert }         = require('../core/insert');
  const { deleteKey }      = require('../core/delete');
  const { search }         = require('../core/search');

  function makeDOM() {
    const dom = new JSDOM(
      '<!DOCTYPE html><body><svg id="svg" width="800" height="600"></svg></body>',
      { url: 'http://localhost' }
    );
    global.document   = dom.window.document;
    global.window     = dom.window;
    global.SVGElement = dom.window.SVGElement;
    try {
      global.navigator = dom.window.navigator;
    } catch (_) {
      Object.defineProperty(global, 'navigator', {
        value: dom.window.navigator, configurable: true, writable: true,
      });
    }
    return dom;
  }

  function buildTree(t, keys) {
    resetIdCounter();
    let state = createTree(t);
    for (const k of keys) {
      const steps = insert(state, k);
      state = steps[steps.length - 1].state;
    }
    return state;
  }

  // Reads the opacity attribute off a g.node-group element.
  // d3 sets it as an attribute (not a style), so getAttribute() works.
  function getNodeOpacity(svgEl, nodeId) {
    const group = svgEl.querySelector(`g[data-node-id="${nodeId}"]`);
    if (!group) return null;
    const val = group.getAttribute('opacity');
    return val === null ? null : parseFloat(val);
  }

  suite('AnimationLayer Stage 6 --, FocusController wired in', () => {
    test('focusController getter returns an instance', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const anim  = new AnimationLayer(svgEl, d3);
      ok(anim.focusController !== null && anim.focusController !== undefined);
      anim.destroy();
    });

    test('render() with INITIAL_STATE leaves all nodes at opacity 1.0', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const anim  = new AnimationLayer(svgEl, d3);

      const state = buildTree(2, [10, 20, 30, 40]);
      const step  = {
        stepIndex: 0, action: ACTIONS.INITIAL_STATE, isKeyStep: false,
        state, highlights: { nodes: [], keys: [], edges: [] },
        explanation: '', pseudocodeLine: 0, variables: {}, meta: {},
      };

      anim.render(step, { ...zeroPlan() });

      for (const nodeId of Object.keys(state.nodes)) {
        const op = getNodeOpacity(svgEl, nodeId);
        // null is fine too --, means no opacity attr = defaults to 1
        ok(op === null || op === 1.0,
          `Node ${nodeId} opacity should be 1.0 after INITIAL_STATE, got ${op}`);
      }
      anim.destroy();
    });

    test('render() with an active highlight --, active node is full, others are dimmed', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const anim  = new AnimationLayer(svgEl, d3);

      const state = buildTree(2, [10, 20, 30, 40]);
      const nodeIds = Object.keys(state.nodes);
      // Pick a leaf to highlight
      const leafId = nodeIds.find(id => state.nodes[id].isLeaf && id !== state.rootId);
      ok(leafId, 'should have a leaf that is not root');

      const step = {
        stepIndex: 0, action: ACTIONS.SEARCH_ENTER_NODE, isKeyStep: false,
        state,
        highlights: { nodes: [{ nodeId: leafId, role: NODE_ROLES.ACTIVE }], keys: [], edges: [] },
        explanation: '', pseudocodeLine: 0, variables: {}, meta: { phase: 'descend', depth: 1 },
      };

      anim.render(step, zeroPlan());

      // Highlighted leaf must be full
      eq(getNodeOpacity(svgEl, leafId), 1.0,
        `Highlighted node ${leafId} should be opacity 1.0`);

      // Root is always full
      eq(getNodeOpacity(svgEl, state.rootId), 1.0,
        `Root ${state.rootId} should always be opacity 1.0`);

      // All other non-root, non-highlighted nodes should be dimmed
      for (const id of nodeIds) {
        if (id === leafId || id === state.rootId) continue;
        const op = getNodeOpacity(svgEl, id);
        eq(op, 0.25, `Non-highlighted node ${id} should be dimmed to 0.25, got ${op}`);
      }

      anim.destroy();
    });

    test('render() with OPERATION_COMPLETE restores all nodes to full opacity', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const anim  = new AnimationLayer(svgEl, d3);

      const state   = buildTree(2, [10, 20, 30, 40]);
      const nodeIds = Object.keys(state.nodes);
      const leafId  = nodeIds.find(id => state.nodes[id].isLeaf && id !== state.rootId);

      // First render: highlight one leaf (dims the rest)
      anim.render({
        stepIndex: 0, action: ACTIONS.SEARCH_ENTER_NODE, isKeyStep: false,
        state,
        highlights: { nodes: [{ nodeId: leafId, role: NODE_ROLES.ACTIVE }], keys: [], edges: [] },
        explanation: '', pseudocodeLine: 0, variables: {}, meta: {},
      }, zeroPlan());

      // Second render: operation complete
      anim.render({
        stepIndex: 1, action: ACTIONS.OPERATION_COMPLETE, isKeyStep: true,
        state, highlights: { nodes: [], keys: [], edges: [] },
        explanation: '', pseudocodeLine: 0, variables: {}, meta: {},
      }, zeroPlan());

      for (const id of nodeIds) {
        const op = getNodeOpacity(svgEl, id);
        ok(op === null || op === 1.0,
          `Node ${id} should be full after OPERATION_COMPLETE, got ${op}`);
      }
      anim.destroy();
    });

    test('render() with all nodes highlighted --, none are dimmed', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const anim  = new AnimationLayer(svgEl, d3);

      const state   = buildTree(2, [10, 20, 30, 40]);
      const nodeIds = Object.keys(state.nodes);
      const allHighlights = nodeIds.map(id => ({ nodeId: id, role: NODE_ROLES.ACTIVE }));

      anim.render({
        stepIndex: 0, action: ACTIONS.SPLIT_EXECUTE, isKeyStep: true,
        state,
        highlights: { nodes: allHighlights, keys: [], edges: [] },
        explanation: '', pseudocodeLine: 0, variables: {}, meta: {},
      }, zeroPlan());

      for (const id of nodeIds) {
        const op = getNodeOpacity(svgEl, id);
        ok(op === null || op === 1.0,
          `All-highlighted node ${id} should be full, got ${op}`);
      }
      anim.destroy();
    });

    test('render() does not throw for any step in a full insert sequence', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const anim  = new AnimationLayer(svgEl, d3);

      const state = buildTree(2, [10, 20, 30]);
      const steps = insert(state, 40);

      let errors = 0;
      for (const step of steps) {
        try { anim.render(step, zeroPlan()); } catch (e) { errors++; console.error(e.message); }
      }
      eq(errors, 0, 'No errors during full insert sequence');
      anim.destroy();
    });

    test('render() does not throw for any step in a full delete sequence', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const anim  = new AnimationLayer(svgEl, d3);

      const state = buildTree(2, [10, 20, 30, 40, 50]);
      const steps = deleteKey(state, 10);

      let errors = 0;
      for (const step of steps) {
        try { anim.render(step, zeroPlan()); } catch (e) { errors++; console.error(e.message); }
      }
      eq(errors, 0, 'No errors during full delete sequence');
      anim.destroy();
    });

    test('render() does not throw for any step in a full search sequence', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const anim  = new AnimationLayer(svgEl, d3);

      const state = buildTree(2, [10, 20, 30, 40, 50]);
      const steps = search(state, 30);

      let errors = 0;
      for (const step of steps) {
        try { anim.render(step, zeroPlan()); } catch (e) { errors++; console.error(e.message); }
      }
      eq(errors, 0, 'No errors during full search sequence');
      anim.destroy();
    });

    test('destroy() with focusController in place does not throw', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const anim  = new AnimationLayer(svgEl, d3);
      anim.destroy();
      ok(true);
    });

    test('root node is always opacity 1.0 during a deep descent', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const anim  = new AnimationLayer(svgEl, d3);

      // Build a taller tree to get 3 levels
      const state = buildTree(2, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
      const nodeIds = Object.keys(state.nodes);

      // Find a deep leaf (not root, not a child of root)
      const rootChildren = state.nodes[state.rootId].children;
      const deepLeaf = nodeIds.find(id => {
        const n = state.nodes[id];
        return n.isLeaf && !rootChildren.includes(id) && id !== state.rootId;
      });

      if (!deepLeaf) {
        ok(true, 'tree not deep enough --, skipping deep leaf test');
        anim.destroy();
        return;
      }

      anim.render({
        stepIndex: 0, action: ACTIONS.SEARCH_ENTER_NODE, isKeyStep: false,
        state,
        highlights: { nodes: [{ nodeId: deepLeaf, role: NODE_ROLES.ACTIVE }], keys: [], edges: [] },
        explanation: '', pseudocodeLine: 0, variables: {}, meta: { phase: 'descend', depth: 2 },
      }, zeroPlan());

      const rootOp = getNodeOpacity(svgEl, state.rootId);
      ok(rootOp === null || rootOp === 1.0,
        `Root should be opacity 1.0 during descent, got ${rootOp}`);

      anim.destroy();
    });
  });
}

// ─────────────────────────────────────────────────────────────────────────────

summary();
process.exit(0);
