// Stage 4 Tests --, Choreographer + FloatLayer + Animated Render
//
// Three sections:
//   1. Choreographer  --, pure Node, no DOM. Verifies every action constant maps
//      to a plan where delays/durations are correct types and key transitions
//      are non-zero for the actions that spec requires animation.
//
//   2. FloatLayer     --, requires jsdom. Verifies arcs are created/removed correctly.
//
//   3. Integration    --, requires jsdom + d3. Verifies AnimationLayer feeds plans
//      from the Choreographer and FloatLayer arcs fire at the right actions.
//
// Run with:
//   node src/tests/choreography.test.js
//
// For sections 2 + 3:
//   npm install jsdom d3

const { test, suite, summary, eq, ok, throws } = require('./runner');
const { ACTIONS, NODE_ROLES, KEY_ROLES }        = require('../core/constants');
const { choreograph, staticPlan }               = require('../choreography/Choreographer');
const { createTheme, TIMINGS }                  = require('../animation/ThemeModule');

// ─── Shared fixtures ──────────────────────────────────────────────────────────

const THEME = createTheme();

function fakeStep(action, overrides = {}) {
  return {
    stepIndex:      0,
    action,
    isKeyStep:      false,
    state: {
      t: 2,
      rootId: 'n1',
      nodes: {
        n1: { id: 'n1', keys: [20], children: ['n2', 'n3'], isLeaf: false, parentId: null },
        n2: { id: 'n2', keys: [10], children: [], isLeaf: true, parentId: 'n1' },
        n3: { id: 'n3', keys: [30], children: [], isLeaf: true, parentId: 'n1' },
      },
    },
    highlights:     { nodes: [], keys: [], edges: [] },
    explanation:    'test',
    pseudocodeLine: 0,
    variables:      { t: 2 },
    meta:           { phase: 'descend', depth: 0 },
    ...overrides,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Section 1 --, Choreographer (zero DOM dependency)
// ─────────────────────────────────────────────────────────────────────────────

suite('choreograph() --, output shape', () => {
  const REQUIRED_KEYS = [
    'nodeEnter', 'nodeExit', 'nodeMove', 'nodeResize',
    'keyEnter',  'keyExit',  'keyMove',
    'edgeEnter', 'edgeExit', 'edgeReroute',
    'highlightFade', 'focusChange', 'cameraPan',
  ];

  test('every action returns an object with all 13 required keys', () => {
    const actions = Object.values(ACTIONS);
    for (const action of actions) {
      const plan = choreograph(null, fakeStep(action), THEME);
      for (const key of REQUIRED_KEYS) {
        ok(plan[key] !== undefined, `Action ${action}: plan missing key "${key}"`);
      }
    }
  });

  test('every plan value has numeric delay and duration', () => {
    const actions = Object.values(ACTIONS);
    for (const action of actions) {
      const plan = choreograph(null, fakeStep(action), THEME);
      for (const [slot, timing] of Object.entries(plan)) {
        ok(
          typeof timing.delay    === 'number',
          `Action ${action}, slot ${slot}: delay should be number, got ${typeof timing.delay}`
        );
        ok(
          typeof timing.duration === 'number',
          `Action ${action}, slot ${slot}: duration should be number, got ${typeof timing.duration}`
        );
        ok(timing.delay    >= 0, `Action ${action}, slot ${slot}: delay must be >= 0`);
        ok(timing.duration >= 0, `Action ${action}, slot ${slot}: duration must be >= 0`);
      }
    }
  });

  test('INITIAL_STATE produces an all-zero plan', () => {
    const plan = choreograph(null, fakeStep(ACTIONS.INITIAL_STATE), THEME);
    for (const [slot, timing] of Object.entries(plan)) {
      eq(timing.delay,    0, `INITIAL_STATE ${slot}.delay should be 0`);
      eq(timing.duration, 0, `INITIAL_STATE ${slot}.duration should be 0`);
    }
  });

  test('OPERATION_COMPLETE produces an all-zero plan', () => {
    const plan = choreograph(null, fakeStep(ACTIONS.OPERATION_COMPLETE), THEME);
    for (const timing of Object.values(plan)) {
      eq(timing.delay,    0);
      eq(timing.duration, 0);
    }
  });

  test('unknown action falls back without throwing', () => {
    const step = fakeStep('TOTALLY_MADE_UP_ACTION');
    const plan = choreograph(null, step, THEME);
    ok(plan);
    ok(typeof plan.nodeEnter.duration === 'number');
  });
});

suite('choreograph() --, staticPlan helper', () => {
  test('staticPlan() returns all 13 keys with delay=0 duration=0', () => {
    const plan = staticPlan();
    const keys = [
      'nodeEnter', 'nodeExit', 'nodeMove', 'nodeResize',
      'keyEnter', 'keyExit', 'keyMove',
      'edgeEnter', 'edgeExit', 'edgeReroute',
      'highlightFade', 'focusChange', 'cameraPan',
    ];
    for (const k of keys) {
      ok(plan[k], `staticPlan missing key "${k}"`);
      eq(plan[k].delay,    0);
      eq(plan[k].duration, 0);
    }
  });
});

suite('choreograph() --, INSERT_INTO_LEAF timing', () => {
  test('keyEnter has non-zero duration', () => {
    const plan = choreograph(null, fakeStep(ACTIONS.INSERT_INTO_LEAF), THEME);
    ok(plan.keyEnter.duration > 0, `INSERT_INTO_LEAF keyEnter.duration should be > 0`);
  });

  test('keyMove has non-zero duration (existing keys shift right)', () => {
    const plan = choreograph(null, fakeStep(ACTIONS.INSERT_INTO_LEAF), THEME);
    ok(plan.keyMove.duration > 0, `INSERT_INTO_LEAF keyMove.duration should be > 0`);
  });

  test('keyEnter fires after highlightFade delay (spec: t=200ms)', () => {
    const plan = choreograph(null, fakeStep(ACTIONS.INSERT_INTO_LEAF), THEME);
    // The spec says new slot appears at t=200ms (after the 200ms highlight)
    ok(plan.keyEnter.delay >= THEME.HIGHLIGHT_FADE_IN,
      `keyEnter.delay (${plan.keyEnter.delay}) should be >= HIGHLIGHT_FADE_IN (${THEME.HIGHLIGHT_FADE_IN})`);
  });
});

suite('choreograph() --, SPLIT_EXECUTE timing', () => {
  test('nodeEnter has non-zero duration (new right-half node)', () => {
    const plan = choreograph(null, fakeStep(ACTIONS.SPLIT_EXECUTE), THEME);
    ok(plan.nodeEnter.duration > 0, 'SPLIT_EXECUTE nodeEnter.duration > 0');
  });

  test('nodeMove has non-zero duration (nodes settle to layout)', () => {
    const plan = choreograph(null, fakeStep(ACTIONS.SPLIT_EXECUTE), THEME);
    ok(plan.nodeMove.duration > 0, 'SPLIT_EXECUTE nodeMove.duration > 0');
  });

  test('edgeEnter fires after nodeMove (edges draw after nodes settle)', () => {
    const plan = choreograph(null, fakeStep(ACTIONS.SPLIT_EXECUTE), THEME);
    ok(
      plan.edgeEnter.delay >= plan.nodeMove.delay,
      `edgeEnter.delay (${plan.edgeEnter.delay}) should be >= nodeMove.delay (${plan.nodeMove.delay})`
    );
  });

  test('total split sequence fits within a reasonable window (< 2000ms)', () => {
    const plan = choreograph(null, fakeStep(ACTIONS.SPLIT_EXECUTE), THEME);
    const latestEnd = Math.max(
      ...Object.values(plan).map(t => t.delay + t.duration)
    );
    ok(latestEnd < 2000, `SPLIT_EXECUTE total time ${latestEnd}ms exceeds 2000ms`);
  });

  test('keyExit fires before nodeEnter (keys leave before new node enters)', () => {
    const plan = choreograph(null, fakeStep(ACTIONS.SPLIT_EXECUTE), THEME);
    ok(
      plan.keyExit.delay <= plan.nodeEnter.delay,
      `keyExit.delay (${plan.keyExit.delay}) should be <= nodeEnter.delay (${plan.nodeEnter.delay})`
    );
  });
});

suite('choreograph() --, PROMOTE_INTO_PARENT timing', () => {
  test('nodeResize fires before keyEnter (expand then arrive)', () => {
    const plan = choreograph(null, fakeStep(ACTIONS.PROMOTE_INTO_PARENT), THEME);
    ok(plan.nodeResize.delay <= plan.keyEnter.delay,
      `nodeResize.delay (${plan.nodeResize.delay}) should be <= keyEnter.delay (${plan.keyEnter.delay})`);
  });

  test('keyEnter has non-zero duration', () => {
    const plan = choreograph(null, fakeStep(ACTIONS.PROMOTE_INTO_PARENT), THEME);
    ok(plan.keyEnter.duration > 0);
  });
});

suite('choreograph() --, BORROW_LEFT_ROTATE / BORROW_RIGHT_ROTATE timing', () => {
  test('keyMove has non-zero duration (arc animation)', () => {
    const planL = choreograph(null, fakeStep(ACTIONS.BORROW_LEFT_ROTATE),  THEME);
    const planR = choreograph(null, fakeStep(ACTIONS.BORROW_RIGHT_ROTATE), THEME);
    ok(planL.keyMove.duration > 0, 'BORROW_LEFT_ROTATE keyMove.duration > 0');
    ok(planR.keyMove.duration > 0, 'BORROW_RIGHT_ROTATE keyMove.duration > 0');
  });

  test('nodeResize fires after keyMove (resize after arc lands)', () => {
    const plan = choreograph(null, fakeStep(ACTIONS.BORROW_LEFT_ROTATE), THEME);
    ok(
      plan.nodeResize.delay >= plan.keyMove.delay,
      `nodeResize.delay (${plan.nodeResize.delay}) should be >= keyMove.delay (${plan.keyMove.delay})`
    );
  });

  test('edgeReroute fires after nodeResize (if internal)', () => {
    const plan = choreograph(null, fakeStep(ACTIONS.BORROW_LEFT_ROTATE), THEME);
    ok(
      plan.edgeReroute.delay >= plan.nodeResize.delay,
      `edgeReroute.delay (${plan.edgeReroute.delay}) >= nodeResize.delay (${plan.nodeResize.delay})`
    );
  });

  test('keyMove delay reflects two highlight phases before arc starts', () => {
    const plan = choreograph(null, fakeStep(ACTIONS.BORROW_LEFT_ROTATE), THEME);
    const expectedMinDelay = THEME.BORROW_HIGHLIGHT_SIBLING + THEME.BORROW_HIGHLIGHT_PARENT;
    ok(
      plan.keyMove.delay >= expectedMinDelay,
      `keyMove.delay (${plan.keyMove.delay}) should be >= ${expectedMinDelay}`
    );
  });
});

suite('choreograph() --, MERGE sequence timing', () => {
  const mergeActions = [
    ACTIONS.MERGE_PREPARE,
    ACTIONS.MERGE_PULL_SEPARATOR,
    ACTIONS.MERGE_ABSORB_KEYS,
    ACTIONS.MERGE_ABSORB_CHILDREN,
    ACTIONS.MERGE_REMOVE_NODE,
    ACTIONS.MERGE_UPDATE_PARENT,
  ];

  for (const action of mergeActions) {
    test(`${action} returns a valid plan`, () => {
      const plan = choreograph(null, fakeStep(action), THEME);
      ok(plan && typeof plan.nodeEnter === 'object');
    });
  }

  test('MERGE_ABSORB_KEYS has non-zero keyMove duration', () => {
    const plan = choreograph(null, fakeStep(ACTIONS.MERGE_ABSORB_KEYS), THEME);
    ok(plan.keyMove.duration > 0, 'MERGE_ABSORB_KEYS keyMove.duration > 0');
  });

  test('MERGE_REMOVE_NODE has non-zero nodeExit duration (dissolve)', () => {
    const plan = choreograph(null, fakeStep(ACTIONS.MERGE_REMOVE_NODE), THEME);
    ok(plan.nodeExit.duration > 0, 'MERGE_REMOVE_NODE nodeExit.duration > 0');
  });

  test('MERGE_PULL_SEPARATOR has non-zero keyMove duration (separator falls)', () => {
    const plan = choreograph(null, fakeStep(ACTIONS.MERGE_PULL_SEPARATOR), THEME);
    ok(plan.keyMove.duration > 0);
  });
});

suite('choreograph() --, ROOT_SHRINK timing', () => {
  test('nodeMove has non-zero duration (child rises)', () => {
    const plan = choreograph(null, fakeStep(ACTIONS.ROOT_SHRINK), THEME);
    ok(plan.nodeMove.duration > 0, 'ROOT_SHRINK nodeMove.duration > 0');
  });

  test('nodeExit fires before nodeMove (old root fades while child rises)', () => {
    const plan = choreograph(null, fakeStep(ACTIONS.ROOT_SHRINK), THEME);
    ok(
      plan.nodeExit.delay <= plan.nodeMove.delay,
      `nodeExit.delay (${plan.nodeExit.delay}) should be <= nodeMove.delay (${plan.nodeMove.delay})`
    );
  });

  test('cameraPan is non-zero (zoom out to show height decrease)', () => {
    const plan = choreograph(null, fakeStep(ACTIONS.ROOT_SHRINK), THEME);
    ok(plan.cameraPan.duration > 0, 'ROOT_SHRINK cameraPan.duration > 0');
  });
});

suite('choreograph() --, search actions have camera/highlight transitions', () => {
  test('SEARCH_ENTER_NODE has cameraPan and highlightFade', () => {
    const plan = choreograph(null, fakeStep(ACTIONS.SEARCH_ENTER_NODE), THEME);
    ok(plan.cameraPan.duration     > 0, 'SEARCH_ENTER_NODE cameraPan.duration > 0');
    ok(plan.highlightFade.duration > 0, 'SEARCH_ENTER_NODE highlightFade.duration > 0');
  });

  test('SEARCH_FOUND restores focus (non-zero focusChange)', () => {
    const plan = choreograph(null, fakeStep(ACTIONS.SEARCH_FOUND), THEME);
    ok(plan.focusChange.duration > 0, 'SEARCH_FOUND focusChange.duration > 0');
  });

  test('SEARCH_NOT_FOUND restores focus', () => {
    const plan = choreograph(null, fakeStep(ACTIONS.SEARCH_NOT_FOUND), THEME);
    ok(plan.focusChange.duration > 0);
  });
});

suite('choreograph() --, delete leaf actions', () => {
  test('DELETE_FROM_LEAF has keyExit duration', () => {
    const plan = choreograph(null, fakeStep(ACTIONS.DELETE_FROM_LEAF), THEME);
    ok(plan.keyExit.duration > 0);
  });

  test('UNDERFLOW_DETECTED dims non-focused nodes (focusChange)', () => {
    const plan = choreograph(null, fakeStep(ACTIONS.UNDERFLOW_DETECTED), THEME);
    ok(plan.focusChange.duration > 0 || plan.highlightFade.duration > 0,
      'UNDERFLOW_DETECTED should have some visual feedback');
  });
});

suite('choreograph() --, timing values use theme constants', () => {
  test('SEARCH_ENTER_NODE cameraPan.duration equals theme.CAMERA_PAN_PER_LEVEL', () => {
    const plan = choreograph(null, fakeStep(ACTIONS.SEARCH_ENTER_NODE), THEME);
    eq(plan.cameraPan.duration, THEME.CAMERA_PAN_PER_LEVEL);
  });

  test('SPLIT_ROOT cameraPan.duration equals theme.CAMERA_ZOOM_OUT', () => {
    const plan = choreograph(null, fakeStep(ACTIONS.SPLIT_ROOT), THEME);
    eq(plan.cameraPan.duration, THEME.CAMERA_ZOOM_OUT);
  });

  test('ROOT_SHRINK cameraPan.duration equals theme.CAMERA_FIT', () => {
    const plan = choreograph(null, fakeStep(ACTIONS.ROOT_SHRINK), THEME);
    eq(plan.cameraPan.duration, THEME.CAMERA_FIT);
  });

  test('SEARCH_ENTER_NODE highlightFade.duration equals theme.HIGHLIGHT_FADE_IN', () => {
    const plan = choreograph(null, fakeStep(ACTIONS.SEARCH_ENTER_NODE), THEME);
    eq(plan.highlightFade.duration, THEME.HIGHLIGHT_FADE_IN);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Section 2 --, FloatLayer (jsdom required)
// ─────────────────────────────────────────────────────────────────────────────

let jsdomAvail = false;
let d3Avail    = false;

try { require('jsdom'); jsdomAvail = true; } catch (_) {}
try { require('d3');    d3Avail    = true; } catch (_) {}

if (!jsdomAvail || !d3Avail) {
  console.log('\nSkipping DOM tests --, run: npm install jsdom d3\n');
} else {
  const { JSDOM } = require('jsdom');

  // Set up globals before requiring d3 (d3 reads navigator on import)
  const _base = new JSDOM('<!DOCTYPE html><body></body>', { url: 'http://localhost' });
  global.window     = _base.window;
  global.document   = _base.window.document;
  global.navigator  = _base.window.navigator;
  global.location   = _base.window.location;
  global.SVGElement = _base.window.SVGElement;

  const d3             = require('d3');
  const { FloatLayer } = require('../animation/FloatLayer');
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
    global.navigator  = dom.window.navigator;
    global.SVGElement = dom.window.SVGElement;
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

  // ── FloatLayer DOM tests ───────────────────────────────────────────────────

  suite('FloatLayer --, DOM structure', () => {
    test('creates a g.float-layer element', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const pG    = d3.select(svgEl).append('g');
      const fl    = new FloatLayer(pG, createTheme(), d3);

      const layer = svgEl.querySelector('g.float-layer');
      ok(layer !== null, 'g.float-layer should exist in DOM');
      fl.destroy();
    });

    test('animateArc inserts a g.float-key element', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const pG    = d3.select(svgEl).append('g');
      const fl    = new FloatLayer(pG, createTheme(), d3);

      fl.animateArc({
        keyValue: 42,
        from: { x: 100, y: 100 },
        to:   { x: 300, y: 50 },
        delay: 0,
        duration: 0, // synchronous for testing
      });

      const floatKeys = svgEl.querySelectorAll('g.float-key');
      ok(floatKeys.length > 0, 'animateArc should create a g.float-key element');
      fl.destroy();
    });

    test('float-key contains a rect and a text element', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const pG    = d3.select(svgEl).append('g');
      const theme = createTheme();
      const fl    = new FloatLayer(pG, theme, d3);

      fl.animateArc({ keyValue: 99, from: { x: 50, y: 50 }, to: { x: 200, y: 200 }, delay: 0, duration: 0 });

      const key  = svgEl.querySelector('g.float-key');
      ok(key !== null, 'float-key group should exist');
      ok(key.querySelector('rect') !== null, 'float-key should have a rect');
      ok(key.querySelector('text') !== null, 'float-key should have a text');
      fl.destroy();
    });

    test('float-key text content matches keyValue', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const pG    = d3.select(svgEl).append('g');
      const fl    = new FloatLayer(pG, createTheme(), d3);

      fl.animateArc({ keyValue: 77, from: { x: 0, y: 0 }, to: { x: 100, y: 100 }, delay: 0, duration: 0 });

      const text = svgEl.querySelector('g.float-key text');
      eq(text?.textContent, '77');
      fl.destroy();
    });

    test('clear() removes all float-key elements', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const pG    = d3.select(svgEl).append('g');
      const fl    = new FloatLayer(pG, createTheme(), d3);

      fl.animateArc({ keyValue: 1, from: { x: 0, y: 0 }, to: { x: 100, y: 0 }, delay: 0, duration: 0 });
      fl.animateArc({ keyValue: 2, from: { x: 0, y: 0 }, to: { x: 200, y: 0 }, delay: 0, duration: 0 });
      ok(svgEl.querySelectorAll('g.float-key').length === 2);

      fl.clear();
      eq(svgEl.querySelectorAll('g.float-key').length, 0, 'clear() should remove all float-key elements');
      fl.destroy();
    });

    test('animateStaggered creates one float-key per key', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const pG    = d3.select(svgEl).append('g');
      const fl    = new FloatLayer(pG, createTheme(), d3);

      fl.animateStaggered(
        [
          { keyValue: 10, from: { x: 0, y: 0 }, to: { x: 100, y: 100 } },
          { keyValue: 20, from: { x: 0, y: 0 }, to: { x: 200, y: 100 } },
          { keyValue: 30, from: { x: 0, y: 0 }, to: { x: 300, y: 100 } },
        ],
        { delay: 0, duration: 0, stagger: 0 }
      );

      eq(svgEl.querySelectorAll('g.float-key').length, 3);
      fl.destroy();
    });

    test('destroy() removes g.float-layer from DOM', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const pG    = d3.select(svgEl).append('g');
      const fl    = new FloatLayer(pG, createTheme(), d3);

      fl.destroy();
      eq(svgEl.querySelectorAll('g.float-layer').length, 0);
    });

    test('multiple animateArc calls each get a unique id', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const pG    = d3.select(svgEl).append('g');
      const fl    = new FloatLayer(pG, createTheme(), d3);

      const id1 = fl.animateArc({ keyValue: 5,  from: { x: 0, y: 0 }, to: { x: 100, y: 0 }, delay: 0, duration: 0 });
      const id2 = fl.animateArc({ keyValue: 10, from: { x: 0, y: 0 }, to: { x: 200, y: 0 }, delay: 0, duration: 0 });
      ok(id1 !== id2, 'each arc should get a unique ID');
      fl.destroy();
    });
  });

  // ── AnimationLayer integration tests ────────────────────────────────────────

  suite('AnimationLayer Stage 4 --, float-layer exists in SVG', () => {
    test('AnimationLayer creates edges, nodes, AND float layers', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const anim  = new AnimationLayer(svgEl, d3);

      ok(svgEl.querySelector('g.edges-layer')  !== null, 'edges-layer missing');
      ok(svgEl.querySelector('g.nodes-layer')  !== null, 'nodes-layer missing');
      ok(svgEl.querySelector('g.float-layer')  !== null, 'float-layer missing');
      anim.destroy();
    });

    test('float-layer is above nodes-layer in DOM order', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const anim  = new AnimationLayer(svgEl, d3);

      const zoomG    = svgEl.querySelector('g.zoom-container');
      const children = Array.from(zoomG.children);
      const edgesIdx = children.findIndex(c => c.classList.contains('edges-layer'));
      const nodesIdx = children.findIndex(c => c.classList.contains('nodes-layer'));
      const floatIdx = children.findIndex(c => c.classList.contains('float-layer'));

      ok(edgesIdx  < nodesIdx,  `edges (${edgesIdx}) should be below nodes (${nodesIdx})`);
      ok(nodesIdx  < floatIdx,  `nodes (${nodesIdx}) should be below float (${floatIdx})`);
      anim.destroy();
    });
  });

  suite('AnimationLayer Stage 4 --, plan flows from Choreographer', () => {
    test('render() does not throw on any action from a real insert sequence', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const anim  = new AnimationLayer(svgEl, d3);

      resetIdCounter();
      const state = buildTree(2, [10, 20, 30]);
      const steps = insert(state, 40); // forces a split

      let errors = 0;
      for (const step of steps) {
        try { anim.render(step); } catch (e) { errors++; console.error(e); }
      }

      eq(errors, 0, 'No errors stepping through a real insert sequence');
      anim.destroy();
    });

    test('render() does not throw on any action from a real delete sequence', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const anim  = new AnimationLayer(svgEl, d3);

      resetIdCounter();
      const state = buildTree(2, [10, 20, 30, 40, 50]);
      const steps = deleteKey(state, 10);

      let errors = 0;
      for (const step of steps) {
        try { anim.render(step); } catch (e) { errors++; console.error(e); }
      }

      eq(errors, 0, 'No errors stepping through a real delete sequence');
      anim.destroy();
    });

    test('render() does not throw on any action from a real search sequence', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const anim  = new AnimationLayer(svgEl, d3);

      resetIdCounter();
      const state = buildTree(2, [10, 20, 30, 40, 50]);
      const steps = search(state, 30);

      let errors = 0;
      for (const step of steps) {
        try { anim.render(step); } catch (e) { errors++; console.error(e); }
      }

      eq(errors, 0);
      anim.destroy();
    });

    test('calling render() twice with different states updates the DOM', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const anim  = new AnimationLayer(svgEl, d3);

      resetIdCounter();
      const state1 = buildTree(2, [10]);
      anim.render({ stepIndex: 0, action: ACTIONS.INITIAL_STATE, isKeyStep: false,
        state: state1, highlights: { nodes: [], keys: [], edges: [] },
        explanation: '', pseudocodeLine: 0, variables: {}, meta: {} });

      const count1 = svgEl.querySelectorAll('g.node-group').length;

      resetIdCounter();
      const state2 = buildTree(2, [10, 20, 30, 40]);
      anim.render({ stepIndex: 1, action: ACTIONS.INITIAL_STATE, isKeyStep: false,
        state: state2, highlights: { nodes: [], keys: [], edges: [] },
        explanation: '', pseudocodeLine: 0, variables: {}, meta: {} });

      const count2 = svgEl.querySelectorAll('g.node-group').length;
      ok(count2 > count1, `node count should grow (${count1} → ${count2})`);
      anim.destroy();
    });

    test('render() clears float elements from previous step', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const anim  = new AnimationLayer(svgEl, d3);

      // Manually add a float key to check it's cleared
      const floatLayer = svgEl.querySelector('g.float-layer');
      const g = dom.window.document.createElementNS('http://www.w3.org/2000/svg', 'g');
      g.classList.add('float-key');
      floatLayer.appendChild(g);
      eq(svgEl.querySelectorAll('g.float-key').length, 1);

      // render() should call floatLayer.clear() at the top
      resetIdCounter();
      const state = buildTree(2, [10]);
      anim.render({ stepIndex: 0, action: ACTIONS.INITIAL_STATE, isKeyStep: false,
        state, highlights: { nodes: [], keys: [], edges: [] },
        explanation: '', pseudocodeLine: 0, variables: {}, meta: {} });

      eq(svgEl.querySelectorAll('g.float-key').length, 0,
        'render() should clear leftover float-key elements from previous step');
      anim.destroy();
    });
  });

  suite('AnimationLayer Stage 4 --, planOverride bypasses Choreographer', () => {
    test('passing planOverride with zero durations renders synchronously', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const anim  = new AnimationLayer(svgEl, d3);

      resetIdCounter();
      const state = buildTree(2, [10, 20, 30, 40]);
      const step  = { stepIndex: 0, action: ACTIONS.INITIAL_STATE, isKeyStep: false,
        state, highlights: { nodes: [], keys: [], edges: [] },
        explanation: '', pseudocodeLine: 0, variables: {}, meta: {} };

      // Static plan --, same as passing nothing but explicit
      const zeroPlan = staticPlan();
      anim.render(step, zeroPlan);

      // With zero durations all attributes should be readable immediately
      const nodeGroups = svgEl.querySelectorAll('g.node-group');
      ok(nodeGroups.length === Object.keys(state.nodes).length);
      anim.destroy();
    });
  });

  suite('AnimationLayer Stage 4 --, destroy cleans up all layers', () => {
    test('destroy() removes zoom-container including float-layer', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const anim  = new AnimationLayer(svgEl, d3);
      anim.destroy();

      eq(svgEl.querySelectorAll('g.zoom-container').length, 0);
      eq(svgEl.querySelectorAll('g.float-layer').length,   0);
    });
  });
}

// ─────────────────────────────────────────────────────────────────────────────

summary();
process.exit(0);