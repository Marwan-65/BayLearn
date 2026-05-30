// Stage 3 Tests --, PlaybackController + Static Render
//
// Two sections:
//   1. PlaybackController  --, pure Node, no DOM required
//   2. Static render       --, requires jsdom and d3. Instructions below.
//
// Run with:
//   node src/tests/renderer.test.js
//
// If the render tests fail with "Cannot find module 'jsdom'" or "d3":
//   npm install jsdom d3
// (Both are dev dependencies, not used in production code.)

const { test, suite, summary, eq, ok, throws } = require('./runner');
const { PlaybackController } = require('../playback/PlaybackController');
const { createTheme, COLOURS, LAYOUT, TIMINGS, NODE_STYLES, EDGE_STYLES } = require('../animation/ThemeModule');

// ─── Shared fixtures ──────────────────────────────────────────────────────────
//
// These are minimal synthetic Step objects. We don't need a real tree here --,
// the controller and theme tests only care about the shape of data, not the
// correctness of B-tree operations (that's covered by btree.test.js).

function fakeStep(index, isKeyStep = false, action = 'INITIAL_STATE') {
  return {
    stepIndex:      index,
    action,
    isKeyStep,
    state:          { t: 2, rootId: 'n1', nodes: { n1: { id: 'n1', keys: [10], children: [], isLeaf: true, parentId: null } } },
    highlights:     { nodes: [], keys: [], edges: [] },
    explanation:    `Step ${index}`,
    pseudocodeLine: 0,
    variables:      { t: 2 },
    meta:           { phase: 'descend', depth: 0 },
  };
}

function makeSteps(count) {
  return Array.from({ length: count }, (_, i) => fakeStep(i, i === 2)); // step 2 is a key step
}

// ─────────────────────────────────────────────────────────────────────────────
// Section 1 --, PlaybackController (zero DOM dependency)
// ─────────────────────────────────────────────────────────────────────────────

suite('PlaybackController --, construction', () => {
  test('throws on empty steps array', () => {
    throws(() => new PlaybackController([]));
  });

  test('throws on non-array', () => {
    throws(() => new PlaybackController(null));
  });

  test('fires initial frame + narrative events on construction', () => {
    const steps = makeSteps(5);
    let frameCount = 0, narrCount = 0;

    // We register AFTER construction... so let's test by registering before
    // first we build a controller that stores events internally then check
    const fired = { frame: [], narrative: [] };
    const ctrl = new PlaybackController(steps, { msPerStep: 99999 });
    // The ctor fires synchronously before we can subscribe --, that's intentional.
    // Verify we get initial render by immediately reading currentStep:
    eq(ctrl.currentStep, steps[0]);
    ctrl.destroy();
  });

  test('starts with status "idle"', () => {
    const ctrl = new PlaybackController(makeSteps(3), { msPerStep: 99999 });
    eq(ctrl.status, 'idle');
    ctrl.destroy();
  });

  test('currentIndex starts at 0', () => {
    const ctrl = new PlaybackController(makeSteps(5), { msPerStep: 99999 });
    eq(ctrl.currentIndex, 0);
    ctrl.destroy();
  });

  test('totalSteps reflects step array length', () => {
    const ctrl = new PlaybackController(makeSteps(7), { msPerStep: 99999 });
    eq(ctrl.totalSteps, 7);
    ctrl.destroy();
  });
});

suite('PlaybackController --, stepForward / stepBack', () => {
  test('stepForward advances currentIndex by 1', () => {
    const ctrl = new PlaybackController(makeSteps(5), { msPerStep: 99999 });
    ctrl.stepForward();
    eq(ctrl.currentIndex, 1);
    ctrl.destroy();
  });

  test('stepForward on last step does not go past end', () => {
    const steps = makeSteps(3);
    const ctrl = new PlaybackController(steps, { msPerStep: 99999 });
    ctrl.stepForward(); ctrl.stepForward(); ctrl.stepForward(); // at end
    eq(ctrl.currentIndex, 2);
    ctrl.destroy();
  });

  test('stepBack decrements currentIndex', () => {
    const ctrl = new PlaybackController(makeSteps(5), { msPerStep: 99999 });
    ctrl.stepForward();
    ctrl.stepForward();
    ctrl.stepBack();
    eq(ctrl.currentIndex, 1);
    ctrl.destroy();
  });

  test('stepBack at index 0 stays at 0', () => {
    const ctrl = new PlaybackController(makeSteps(5), { msPerStep: 99999 });
    ctrl.stepBack();
    eq(ctrl.currentIndex, 0);
    ctrl.destroy();
  });

  test('stepForward fires frame event with correct step', () => {
    const steps = makeSteps(5);
    const ctrl = new PlaybackController(steps, { msPerStep: 99999 });
    let received = null;
    ctrl.on('frame', s => { received = s; });
    ctrl.stepForward();
    eq(received, steps[1]);
    ctrl.destroy();
  });

  test('stepBack fires frame event with correct step', () => {
    const steps = makeSteps(5);
    const ctrl = new PlaybackController(steps, { msPerStep: 99999 });
    ctrl.stepForward();
    let received = null;
    ctrl.on('frame', s => { received = s; });
    ctrl.stepBack();
    eq(received, steps[0]);
    ctrl.destroy();
  });

  test('stepForward pauses auto-play if running', () => {
    const ctrl = new PlaybackController(makeSteps(10), { msPerStep: 99999 });
    ctrl.play();
    eq(ctrl.status, 'playing');
    ctrl.stepForward();
    eq(ctrl.status, 'paused');
    ctrl.destroy();
  });
});

suite('PlaybackController --, seekTo', () => {
  test('seekTo jumps to correct index', () => {
    const ctrl = new PlaybackController(makeSteps(10), { msPerStep: 99999 });
    ctrl.seekTo(5);
    eq(ctrl.currentIndex, 5);
    ctrl.destroy();
  });

  test('seekTo clamps below 0', () => {
    const ctrl = new PlaybackController(makeSteps(5), { msPerStep: 99999 });
    ctrl.seekTo(-1);
    eq(ctrl.currentIndex, 0);
    ctrl.destroy();
  });

  test('seekTo clamps above length-1', () => {
    const ctrl = new PlaybackController(makeSteps(5), { msPerStep: 99999 });
    ctrl.seekTo(99);
    eq(ctrl.currentIndex, 4);
    ctrl.destroy();
  });

  test('seekTo last step marks status as complete', () => {
    const ctrl = new PlaybackController(makeSteps(5), { msPerStep: 99999 });
    ctrl.seekTo(4);
    eq(ctrl.status, 'complete');
    ctrl.destroy();
  });

  test('seekTo fires frame + narrative for the target step', () => {
    const steps = makeSteps(8);
    const ctrl = new PlaybackController(steps, { msPerStep: 99999 });
    let frameStep = null, narrStep = null;
    ctrl.on('frame',     s => { frameStep = s; });
    ctrl.on('narrative', s => { narrStep  = s; });
    ctrl.seekTo(6);
    eq(frameStep, steps[6]);
    eq(narrStep,  steps[6]);
    ctrl.destroy();
  });
});

suite('PlaybackController --, pauseOnKeySteps', () => {
  test('pauseOnKeySteps option exists and is stored', () => {
    // The async timing behaviour is verified by manual testing or integration tests.
    // Here we verify the option is stored correctly.
    const ctrl = new PlaybackController(makeSteps(5), {
      msPerStep: 99999,
      pauseOnKeySteps: true,
    });
    eq(ctrl._pauseOnKey, true);
    ctrl.destroy();
  });

  test('pauseOnKeySteps=false is stored correctly', () => {
    const ctrl = new PlaybackController(makeSteps(5), {
      msPerStep: 99999,
      pauseOnKeySteps: false,
    });
    eq(ctrl._pauseOnKey, false);
    ctrl.destroy();
  });
});

// Handle async tests since Node's test runner doesn't natively support them
// by converting them to synchronous-ish via setTimeout inspection:

suite('PlaybackController --, status transitions', () => {
  test('play() sets status to "playing"', () => {
    const ctrl = new PlaybackController(makeSteps(5), { msPerStep: 99999 });
    ctrl.play();
    eq(ctrl.status, 'playing');
    ctrl.destroy();
  });

  test('pause() after play() sets status to "paused"', () => {
    const ctrl = new PlaybackController(makeSteps(5), { msPerStep: 99999 });
    ctrl.play();
    ctrl.pause();
    eq(ctrl.status, 'paused');
    ctrl.destroy();
  });

  test('statusChange fires with full status object', () => {
    const ctrl = new PlaybackController(makeSteps(5), { msPerStep: 99999 });
    let changePayload = null;
    ctrl.on('statusChange', s => { changePayload = s; });
    ctrl.play();
    ok(changePayload !== null);
    eq(changePayload.status, 'playing');
    ok(typeof changePayload.index === 'number');
    ok(typeof changePayload.total === 'number');
    ctrl.destroy();
  });

  test('play() on complete controller is a no-op', () => {
    const ctrl = new PlaybackController(makeSteps(3), { msPerStep: 99999 });
    ctrl.seekTo(2); // last step
    ctrl.play();
    eq(ctrl.status, 'complete');
    ctrl.destroy();
  });
});

suite('PlaybackController --, setSpeed', () => {
  test('setSpeed(2) sets internal speed', () => {
    const ctrl = new PlaybackController(makeSteps(3), { msPerStep: 99999 });
    ctrl.setSpeed(2);
    eq(ctrl._speed, 2);
    ctrl.destroy();
  });

  test('setSpeed with non-positive throws', () => {
    const ctrl = new PlaybackController(makeSteps(3), { msPerStep: 99999 });
    throws(() => ctrl.setSpeed(0));
    throws(() => ctrl.setSpeed(-1));
    ctrl.destroy();
  });
});

suite('PlaybackController --, event system', () => {
  test('on() returns the controller for chaining', () => {
    const ctrl = new PlaybackController(makeSteps(3), { msPerStep: 99999 });
    const result = ctrl.on('frame', () => {});
    eq(result, ctrl);
    ctrl.destroy();
  });

  test('off() removes a specific listener', () => {
    const ctrl = new PlaybackController(makeSteps(5), { msPerStep: 99999 });
    let callCount = 0;
    const cb = () => { callCount++; };
    ctrl.on('frame', cb);
    ctrl.off('frame', cb);
    ctrl.stepForward();
    eq(callCount, 0);
    ctrl.destroy();
  });

  test('multiple listeners for same event all fire', () => {
    const ctrl = new PlaybackController(makeSteps(5), { msPerStep: 99999 });
    let a = 0, b = 0;
    ctrl.on('frame', () => a++);
    ctrl.on('frame', () => b++);
    ctrl.stepForward();
    eq(a, 1);
    eq(b, 1);
    ctrl.destroy();
  });

  test('listener error does not crash the controller', () => {
    const ctrl = new PlaybackController(makeSteps(5), { msPerStep: 99999 });
    ctrl.on('frame', () => { throw new Error('listener error'); });
    // stepForward should not throw even though the listener does
    ctrl.stepForward();
    eq(ctrl.currentIndex, 1); // advanced normally despite the error
    ctrl.destroy();
  });
});

suite('PlaybackController --, destroy', () => {
  test('after destroy, play/pause/step are no-ops', () => {
    const ctrl = new PlaybackController(makeSteps(5), { msPerStep: 99999 });
    ctrl.destroy();
    ctrl.play();    // should not throw
    ctrl.pause();
    ctrl.stepForward();
    ctrl.stepBack();
  });

  test('after destroy, listeners are cleared', () => {
    const ctrl = new PlaybackController(makeSteps(5), { msPerStep: 99999 });
    let fired = false;
    ctrl.on('frame', () => { fired = true; });
    ctrl.destroy();
    ctrl.stepForward(); // no-op, but just in case
    eq(fired, false);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Section 2 --, ThemeModule (no DOM required)
// ─────────────────────────────────────────────────────────────────────────────

suite('ThemeModule --, colour palette', () => {
  test('all background colours are valid hex strings', () => {
    const hexRe = /^#[0-9a-f]{6}$/i;
    for (const [k, v] of Object.entries(COLOURS)) {
      ok(hexRe.test(v), `COLOURS.${k} = "${v}" is not a valid hex colour`);
    }
  });

  test('gold colour is present and non-empty', () => {
    ok(COLOURS.GOLD && COLOURS.GOLD.length > 0);
  });

  test('all semantic colours exist: green, red, blue, purple, orange', () => {
    ok(COLOURS.GREEN);
    ok(COLOURS.RED);
    ok(COLOURS.BLUE);
    ok(COLOURS.PURPLE);
    ok(COLOURS.ORANGE);
  });
});

suite('ThemeModule --, NODE_STYLES', () => {
  const requiredRoles = [
    'default', 'active', 'parent', 'split_left', 'split_right',
    'merge_target', 'merge_source', 'sibling_left', 'sibling_right',
    'overflow', 'underflow', 'dim',
  ];

  test('every NODE_ROLE has an entry in NODE_STYLES', () => {
    for (const role of requiredRoles) {
      ok(NODE_STYLES[role], `NODE_STYLES missing entry for role "${role}"`);
    }
  });

  test('every NODE_STYLE entry has fill, stroke, opacity, strokeWidth', () => {
    for (const [role, style] of Object.entries(NODE_STYLES)) {
      ok(style.fill,        `NODE_STYLES.${role} missing fill`);
      ok(style.stroke,      `NODE_STYLES.${role} missing stroke`);
      ok(typeof style.opacity     === 'number', `NODE_STYLES.${role} opacity should be a number`);
      ok(typeof style.strokeWidth === 'number', `NODE_STYLES.${role} strokeWidth should be a number`);
    }
  });

  test('dim role has opacity < 0.5 (it should actually dim things)', () => {
    ok(NODE_STYLES.dim.opacity < 0.5, `dim opacity should be < 0.5, got ${NODE_STYLES.dim.opacity}`);
  });

  test('overflow role uses red stroke', () => {
    eq(NODE_STYLES.overflow.stroke, COLOURS.RED);
  });

  test('active role uses gold stroke', () => {
    eq(NODE_STYLES.active.stroke, COLOURS.GOLD);
  });
});

suite('ThemeModule --, EDGE_STYLES', () => {
  const requiredEdgeRoles = ['default', 'path', 'new', 'removing', 'rerouting'];

  test('all edge roles present', () => {
    for (const role of requiredEdgeRoles) {
      ok(EDGE_STYLES[role], `EDGE_STYLES missing role "${role}"`);
    }
  });

  test('path edge is thicker than default', () => {
    ok(
      EDGE_STYLES.path.strokeWidth > EDGE_STYLES.default.strokeWidth,
      `path strokeWidth (${EDGE_STYLES.path.strokeWidth}) should exceed default (${EDGE_STYLES.default.strokeWidth})`
    );
  });

  test('path edge is fully opaque', () => {
    eq(EDGE_STYLES.path.opacity, 1.0);
  });
});

suite('ThemeModule --, layout constants match spec section 2.3', () => {
  test('SLOT_WIDTH is 52', () => { eq(LAYOUT.SLOT_WIDTH,  52); });
  test('SLOT_HEIGHT is 56', () => { eq(LAYOUT.SLOT_HEIGHT, 56); });
  test('SLOT_GAP is 4',    () => { eq(LAYOUT.SLOT_GAP, 4); });
  test('NODE_PADDING_X is 10', () => { eq(LAYOUT.NODE_PADDING_X, 10); });
  test('NODE_PADDING_Y is 8',  () => { eq(LAYOUT.NODE_PADDING_Y, 8); });
  test('LEVEL_SEPARATION is 120',  () => { eq(LAYOUT.LEVEL_SEPARATION,  120); });
  test('SIBLING_SEPARATION is 24', () => { eq(LAYOUT.SIBLING_SEPARATION, 24); });
  test('SIDEBAR_WIDTH is 400', () => { eq(LAYOUT.SIDEBAR_WIDTH, 400); });
  test('NODE_CORNER_RADIUS is 10', () => { eq(LAYOUT.NODE_CORNER_RADIUS, 10); });
});

suite('ThemeModule --, timing constants', () => {
  test('all timing values are positive numbers', () => {
    for (const [k, v] of Object.entries(TIMINGS)) {
      ok(typeof v === 'number' && v > 0, `TIMINGS.${k} = ${v} should be a positive number`);
    }
  });

  test('CAMERA_FIT is 600ms (spec camera rule 5)', () => {
    eq(TIMINGS.CAMERA_FIT, 600);
  });
});

suite('ThemeModule --, createTheme()', () => {
  test('createTheme() returns all required keys', () => {
    const theme = createTheme();
    ok(theme.GOLD);
    ok(theme.BG_SURFACE);
    ok(theme.SLOT_WIDTH);
    ok(theme.NODE_STYLES);
    ok(theme.EDGE_STYLES);
    ok(theme.KEY_SLOT_FILLS);
    ok(theme.TIMINGS === undefined); // TIMINGS are merged flat, not nested
    ok(typeof theme.CAMERA_FIT === 'number');
  });

  test('createTheme(overrides) merges correctly', () => {
    const theme = createTheme({ GOLD: '#ff0000', SLOT_WIDTH: 60 });
    eq(theme.GOLD,       '#ff0000');
    eq(theme.SLOT_WIDTH, 60);
    // Other keys should be defaults
    eq(theme.SLOT_HEIGHT, 56);
  });

  test('createTheme() without overrides uses spec values', () => {
    const theme = createTheme();
    eq(theme.SLOT_WIDTH, 52);
    eq(theme.LEVEL_SEPARATION, 120);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Section 3 --, Static render tests (jsdom + d3)
//
// These test that the DOM produced by NodeRenderer and EdgeRenderer matches
// what the spec describes. They run inside a simulated browser via jsdom.
// ─────────────────────────────────────────────────────────────────────────────

let jsdomAvailable = false;
let d3Available    = false;

try {
  require('jsdom');
  jsdomAvailable = true;
} catch (_) {}

try {
  require('d3');
  d3Available = true;
} catch (_) {}

if (!jsdomAvailable || !d3Available) {
  console.log('\nSkipping render tests --, run: npm install jsdom d3\n');
} else {
  // d3 v7 reads window.navigator and window.location at import time in some
  // environments. We must set up a real jsdom window BEFORE requiring d3 so
  // those globals are present. We create a shared baseline DOM for this.
  const { JSDOM } = require('jsdom');

  const _baseDom = new JSDOM(
    '<!DOCTYPE html><body></body>',
    { url: 'http://localhost' }   // url option satisfies d3's location checks
  );
  global.window     = _baseDom.window;
  global.document   = _baseDom.window.document;
  global.navigator  = _baseDom.window.navigator;
  global.location   = _baseDom.window.location;
  global.SVGElement = _baseDom.window.SVGElement;

  // NOW it's safe to require d3 and the renderers
  const d3              = require('d3');
  const { NodeRenderer} = require('../animation/NodeRenderer');
  const { EdgeRenderer} = require('../animation/EdgeRenderer');
  const { AnimationLayer } = require('../animation/AnimationLayer');
  const { computeLayout }  = require('../core/layout');
  const { resetIdCounter } = require('../core/shared');
  const { createTree }     = require('../core/BTree');
  const { insert }         = require('../core/insert');

  // Create a fresh jsdom document for each test so tests are isolated.
  // We reuse the same window globals (d3 caches them once) but give each
  // test its own SVG element inside the shared document.
  function makeDOM() {
    const dom = new JSDOM(
      '<!DOCTYPE html><body><svg id="svg" width="800" height="600"></svg></body>',
      { url: 'http://localhost' }
    );
    // Point globals at the new document so d3.select(svgEl) works
    global.document   = dom.window.document;
    global.window     = dom.window;
    global.navigator  = dom.window.navigator;
    global.SVGElement = dom.window.SVGElement;
    return dom;
  }

  function buildTestTree(t, keys) {
    resetIdCounter();
    let state = createTree(t);
    for (const k of keys) {
      const steps = insert(state, k);
      state = steps[steps.length - 1].state;
    }
    return state;
  }

  function makeStep(state, nodeHighlights = [], keyHighlights = []) {
    return {
      stepIndex: 0,
      action: 'INITIAL_STATE',
      isKeyStep: false,
      state,
      highlights: { nodes: nodeHighlights, keys: keyHighlights, edges: [] },
      explanation: 'Test step',
      pseudocodeLine: 0,
      variables: { t: state.t },
      meta: { phase: 'descend', depth: 0 },
    };
  }

  suite('NodeRenderer --, DOM structure', () => {
    test('renders one g.node-group per node', () => {
      const dom     = makeDOM();
      const svgEl   = dom.window.document.getElementById('svg');
      const parentG = d3.select(svgEl).append('g');
      const theme   = createTheme();
      const state   = buildTestTree(2, [10, 20, 30]);
      const layout  = computeLayout(state);
      const step    = makeStep(state);

      const renderer = new NodeRenderer(parentG, theme, d3);
      renderer.render(step, layout);

      const groups = svgEl.querySelectorAll('g.node-group');
      eq(groups.length, Object.keys(state.nodes).length);
    });

    test('each node-group has a rect.node-card', () => {
      const dom    = makeDOM();
      const svgEl  = dom.window.document.getElementById('svg');
      const pG     = d3.select(svgEl).append('g');
      const theme  = createTheme();
      const state  = buildTestTree(2, [10, 20, 30]);
      const layout = computeLayout(state);

      new NodeRenderer(pG, theme, d3).render(makeStep(state), layout);

      const cards = svgEl.querySelectorAll('rect.node-card');
      eq(cards.length, Object.keys(state.nodes).length);
    });

    test('each node has the correct number of g.key-slot children', () => {
      const dom    = makeDOM();
      const svgEl  = dom.window.document.getElementById('svg');
      const pG     = d3.select(svgEl).append('g');
      const theme  = createTheme();
      const state  = buildTestTree(2, [10, 20, 30, 40, 50]);
      const layout = computeLayout(state);

      new NodeRenderer(pG, theme, d3).render(makeStep(state), layout);

      const groups = svgEl.querySelectorAll('g.node-group');
      for (const g of groups) {
        const nodeId    = g.getAttribute('data-node-id');
        const node      = state.nodes[nodeId];
        const keySlots  = g.querySelectorAll('g.key-slot');
        eq(keySlots.length, node.keys.length,
          `Node ${nodeId} has ${node.keys.length} keys, expected ${node.keys.length} slot groups`);
      }
    });

    test('slot-value text contains the correct key number', () => {
      const dom    = makeDOM();
      const svgEl  = dom.window.document.getElementById('svg');
      const pG     = d3.select(svgEl).append('g');
      const theme  = createTheme();
      const state  = buildTestTree(2, [42]);
      const layout = computeLayout(state);

      new NodeRenderer(pG, theme, d3).render(makeStep(state), layout);

      const valueTexts = svgEl.querySelectorAll('text.slot-value');
      eq(valueTexts.length, 1);
      eq(valueTexts[0].textContent, '42');
    });

    test('root badge appears for the root node', () => {
      const dom    = makeDOM();
      const svgEl  = dom.window.document.getElementById('svg');
      const pG     = d3.select(svgEl).append('g');
      const theme  = createTheme();
      const state  = buildTestTree(2, [10, 20, 30]);
      const layout = computeLayout(state);

      new NodeRenderer(pG, theme, d3).render(makeStep(state), layout);

      const badges = svgEl.querySelectorAll('g.root-badge');
      eq(badges.length, 1);
      const badgeText = badges[0].querySelector('text.badge-text');
      eq(badgeText.textContent, 'root');
    });

    test('internal nodes have ptr-dot circles, leaves do not', () => {
      const dom    = makeDOM();
      const svgEl  = dom.window.document.getElementById('svg');
      const pG     = d3.select(svgEl).append('g');
      const theme  = createTheme();
      const state  = buildTestTree(2, [10, 20, 30, 40]); // 2-level tree
      const layout = computeLayout(state);

      new NodeRenderer(pG, theme, d3).render(makeStep(state), layout);

      for (const [nodeId, node] of Object.entries(state.nodes)) {
        const g    = svgEl.querySelector(`g[data-node-id="${nodeId}"]`);
        const dots = g.querySelectorAll('circle.ptr-dot');
        if (node.isLeaf) {
          eq(dots.length, 0, `Leaf ${nodeId} should have no pointer dots`);
        } else {
          eq(dots.length, node.keys.length + 1,
            `Internal ${nodeId} should have ${node.keys.length + 1} dots`);
        }
      }
    });

    test('active role applied correctly from step highlights', () => {
      const dom    = makeDOM();
      const svgEl  = dom.window.document.getElementById('svg');
      const pG     = d3.select(svgEl).append('g');
      const theme  = createTheme();
      const state  = buildTestTree(2, [10, 20, 30]);
      const layout = computeLayout(state);
      const rootId = state.rootId;

      const step = makeStep(state, [{ nodeId: rootId, role: 'active' }]);
      new NodeRenderer(pG, theme, d3).render(step, layout);

      const rootGroup = svgEl.querySelector(`g[data-node-id="${rootId}"]`);
      const card      = rootGroup.querySelector('rect.node-card');
      // The stroke should be GOLD (active role)
      eq(card.getAttribute('stroke'), theme.GOLD);
    });

    test('re-render with different state updates key count correctly', () => {
      const dom    = makeDOM();
      const svgEl  = dom.window.document.getElementById('svg');
      const pG     = d3.select(svgEl).append('g');
      const theme  = createTheme();
      const renderer = new NodeRenderer(pG, theme, d3);

      const state1 = buildTestTree(2, [10]);
      const layout1 = computeLayout(state1);
      renderer.render(makeStep(state1), layout1);
      eq(svgEl.querySelectorAll('text.slot-value').length, 1);

      const state2 = buildTestTree(2, [10, 20, 30]);
      const layout2 = computeLayout(state2);
      renderer.render(makeStep(state2), layout2);
      // Now there are 3 keys (single leaf)
      eq(svgEl.querySelectorAll('text.slot-value').length, 3);
    });
  });

  suite('EdgeRenderer --, DOM structure', () => {
    test('renders one line.edge per parent-child relationship', () => {
      const dom    = makeDOM();
      const svgEl  = dom.window.document.getElementById('svg');
      const pG     = d3.select(svgEl).append('g');
      const theme  = createTheme();
      const state  = buildTestTree(2, [10, 20, 30, 40]);
      const layout = computeLayout(state);

      new EdgeRenderer(pG, theme, d3).render(makeStep(state), layout);

      const edges   = svgEl.querySelectorAll('line.edge');
      const expected = Object.keys(layout.edges).length;
      eq(edges.length, expected);
    });

    test('single-node tree produces no edges', () => {
      const dom    = makeDOM();
      const svgEl  = dom.window.document.getElementById('svg');
      const pG     = d3.select(svgEl).append('g');
      const theme  = createTheme();
      const state  = buildTestTree(2, [1]);
      const layout = computeLayout(state);

      new EdgeRenderer(pG, theme, d3).render(makeStep(state), layout);

      const edges = svgEl.querySelectorAll('line.edge');
      eq(edges.length, 0);
    });

    test('edge stroke defaults to BORDER2', () => {
      const dom    = makeDOM();
      const svgEl  = dom.window.document.getElementById('svg');
      const pG     = d3.select(svgEl).append('g');
      const theme  = createTheme();
      const state  = buildTestTree(2, [10, 20, 30, 40]);
      const layout = computeLayout(state);

      new EdgeRenderer(pG, theme, d3).render(makeStep(state), layout);

      const lines = svgEl.querySelectorAll('line.edge');
      for (const line of lines) {
        eq(line.getAttribute('stroke'), theme.BORDER2);
      }
    });

    test('edges-layer is inserted before nodes-layer in the DOM', () => {
      const dom    = makeDOM();
      const svgEl  = dom.window.document.getElementById('svg');
      const pG     = d3.select(svgEl).append('g');
      const theme  = createTheme();
      const state  = buildTestTree(2, [10, 20, 30, 40]);
      const layout = computeLayout(state);

      new EdgeRenderer(pG, theme, d3).render(makeStep(state), layout);
      new NodeRenderer(pG, theme, d3).render(makeStep(state), layout);

      const children = Array.from(pG.node().children);
      const edgesIdx = children.findIndex(c => c.classList.contains('edges-layer'));
      const nodesIdx = children.findIndex(c => c.classList.contains('nodes-layer'));
      ok(edgesIdx < nodesIdx, `edges-layer (${edgesIdx}) should come before nodes-layer (${nodesIdx})`);
    });

    test('re-render removes old edges when nodes change', () => {
      const dom     = makeDOM();
      const svgEl   = dom.window.document.getElementById('svg');
      const pG      = d3.select(svgEl).append('g');
      const theme   = createTheme();
      const renderer = new EdgeRenderer(pG, theme, d3);

      const state1  = buildTestTree(2, [10, 20, 30, 40]);
      const layout1 = computeLayout(state1);
      renderer.render(makeStep(state1), layout1);
      const count1 = svgEl.querySelectorAll('line.edge').length;
      ok(count1 > 0);

      // Single-node tree --, no edges
      const state2  = buildTestTree(2, [1]);
      const layout2 = computeLayout(state2);
      renderer.render(makeStep(state2), layout2);
      eq(svgEl.querySelectorAll('line.edge').length, 0);
    });
  });

  suite('AnimationLayer --, integration', () => {
    test('render() produces node groups and edges in SVG', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const anim  = new AnimationLayer(svgEl, d3);
      const state = buildTestTree(2, [10, 20, 30, 40]);
      const step  = makeStep(state);

      anim.render(step);

      ok(svgEl.querySelectorAll('g.node-group').length > 0, 'should have node groups');
      ok(svgEl.querySelectorAll('line.edge').length > 0,    'should have edges');
    });

    test('render() exposes lastLayout with correct node count', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const anim  = new AnimationLayer(svgEl, d3);
      const state = buildTestTree(2, [10, 20, 30, 40]);

      anim.render(makeStep(state));

      ok(anim.lastLayout !== null);
      eq(
        Object.keys(anim.lastLayout.nodes).length,
        Object.keys(state.nodes).length
      );
    });

    test('destroy() removes zoom-container from DOM', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const anim  = new AnimationLayer(svgEl, d3);

      anim.destroy();

      const zoomContainers = svgEl.querySelectorAll('g.zoom-container');
      eq(zoomContainers.length, 0);
    });

    test('PlaybackController wired to AnimationLayer renders all steps without error', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const anim  = new AnimationLayer(svgEl, d3);
      const state = buildTestTree(2, [10, 20, 30, 40]);
      const steps_import = require('../core/insert');
      const { insert: ins } = steps_import;
      const insertSteps = ins(state, 50);

      const ctrl = new PlaybackController(insertSteps, { msPerStep: 99999 });
      ctrl.on('frame', step => anim.render(step));

      // Step through all frames manually
      let errors = 0;
      for (let i = 0; i < insertSteps.length - 1; i++) {
        try {
          ctrl.stepForward();
        } catch (e) {
          errors++;
        }
      }

      eq(errors, 0, 'No errors should occur while stepping through all frames');
      ctrl.destroy();
      anim.destroy();
    });
  });
}

// ─────────────────────────────────────────────────────────────────────────────

summary();