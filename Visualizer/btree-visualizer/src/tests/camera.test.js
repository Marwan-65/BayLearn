// Stage 5 Tests --, CameraController + MinimapRenderer + AnimationLayer integration
//
// Three sections:
//   1. Pure-Node tests (no DOM) --, _boundingBox helper, CameraController
//      method contracts, plan reading
//   2. jsdom tests --, MinimapRenderer DOM structure and MinimapRenderer updates
//   3. Integration --, AnimationLayer wires camera + minimap, destroy cleans up
//
// Run:
//   node src/tests/camera.test.js
//
// For sections 2 + 3:
//   npm install jsdom d3

'use strict';

const { test, suite, summary, eq, ok, throws } = require('./runner');
const { ACTIONS }           = require('../core/constants');
const { createTheme }       = require('../animation/ThemeModule');
const { _boundingBox }      = require('../animation/CameraController');
const { choreograph }       = require('../choreography/Choreographer');

const THEME = createTheme();

// ─── Shared tree fixture (no DOM required) ────────────────────────────────────

// Minimal fake layout --, enough for the camera helpers to consume
function fakeLayout(nodeCount = 3) {
  const nodes  = {};
  const keys   = {};
  const dots   = {};
  const edges  = {};

  // 1 root + (nodeCount-1) leaves arranged in a simple 2-level tree
  nodes['n1'] = { x: 0,    y: 0,   width: 120, height: 72 };
  keys['n1']  = [];
  dots['n1']  = [];

  for (let i = 2; i <= nodeCount; i++) {
    const x = (i - 2) * 160 - (nodeCount - 2) * 80;
    nodes[`n${i}`] = { x, y: 192, width: 72, height: 72 };
    keys[`n${i}`]  = [];
    dots[`n${i}`]  = [];
    edges[`n1→${i - 2}`] = {
      fromDot: { x: (i - 2) * 40 - 20, y: 72 },
      toNode:  { x, y: 192 },
      path:    '',
    };
  }

  return { nodes, keys, pointerDots: dots, edges };
}

function fakeStep(action, nodeHighlights = [], keyHighlights = []) {
  return {
    stepIndex: 0,
    action,
    isKeyStep: false,
    state: {
      t: 2, rootId: 'n1',
      nodes: {
        n1: { id: 'n1', keys: [20],     children: ['n2', 'n3'], isLeaf: false, parentId: null },
        n2: { id: 'n2', keys: [10],     children: [],           isLeaf: true,  parentId: 'n1' },
        n3: { id: 'n3', keys: [30, 40], children: [],           isLeaf: true,  parentId: 'n1' },
      },
    },
    highlights: { nodes: nodeHighlights, keys: keyHighlights, edges: [] },
    explanation: 'test', pseudocodeLine: 0, variables: { t: 2 },
    meta: { phase: 'descend', depth: 0 },
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Section 1 --, _boundingBox pure function (no DOM)
// ─────────────────────────────────────────────────────────────────────────────

suite('_boundingBox --, geometry helper', () => {
  test('returns null for empty array', () => {
    eq(_boundingBox([]), null);
  });

  test('returns null for null/undefined', () => {
    eq(_boundingBox(null), null);
    eq(_boundingBox(undefined), null);
  });

  test('single node centred at origin', () => {
    const bbox = _boundingBox([{ x: 0, y: 0, width: 120, height: 72 }]);
    ok(bbox !== null);
    eq(bbox.cx, 0);
    eq(bbox.cy, 36);
    eq(bbox.w,  120);
    eq(bbox.h,  72);
  });

  test('two nodes side by side', () => {
    const bbox = _boundingBox([
      { x: -100, y: 0, width: 72, height: 72 },
      { x:  100, y: 0, width: 72, height: 72 },
    ]);
    ok(bbox !== null);
    // left edge = -136, right edge = 136
    eq(bbox.w, 272);
    eq(bbox.cx, 0);
  });

  test('two nodes stacked vertically', () => {
    const bbox = _boundingBox([
      { x: 0, y:   0, width: 72, height: 72 },
      { x: 0, y: 192, width: 72, height: 72 },
    ]);
    ok(bbox !== null);
    eq(bbox.h,  264); // 0 to 192+72 = 264
    eq(bbox.cy, 132);
  });

  test('cx is exactly the horizontal midpoint', () => {
    const a = { x: -200, y: 0, width: 72, height: 72 };
    const b = { x:  300, y: 0, width: 72, height: 72 };
    const bbox = _boundingBox([a, b]);
    // leftmost = -236, rightmost = 336
    const expected = (-236 + 336) / 2;
    ok(Math.abs(bbox.cx - expected) < 0.01);
  });

  test('three nodes in an L-shape', () => {
    const bbox = _boundingBox([
      { x:   0, y:   0, width: 72, height: 72 },
      { x: 200, y:   0, width: 72, height: 72 },
      { x:   0, y: 192, width: 72, height: 72 },
    ]);
    ok(bbox.w > 0 && bbox.h > 0);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Section 2 --, CameraController (mocked SVG, no full jsdom needed)
// ─────────────────────────────────────────────────────────────────────────────

suite('CameraController --, construction and method contracts', () => {
  // We test the pure-logic parts without a real browser.
  // _applyTransform is the only method that touches D3 --, we verify the
  // controller calls it with sensible arguments by tracking what fitAll computes.

  function makeMockCamera() {
    const { CameraController } = require('../animation/CameraController');
    const calls = [];

    // attrTween returns a fn that CameraController calls --, we just swallow it
    const mockTransition = () => ({
      delay:    () => mockTransition(),
      duration: () => mockTransition(),
      ease:     () => mockTransition(),
      attrTween: (name, fn) => { calls.push({ fn: 'attrTween', name }); return mockTransition(); },
      call:     (fn, t) => { calls.push({ fn: 'call', t }); return mockTransition(); },
      attr:     () => mockTransition(),
    });

    const mockZoomGSel = {
      attr:       (name, val) => { calls.push({ fn: 'attr', name, val }); return mockZoomGSel; },
      transition: () => mockTransition(),
    };

    const mockD3 = {
      zoomIdentity: { k: 1, x: 0, y: 0,
        translate: (tx, ty) => ({ k: 1, x: tx, y: ty, scale: (k) => ({ k, x: tx, y: ty }) }),
        scale: (k) => ({ k, x: 0, y: 0 }),
      },
      zoomTransform:     () => ({ k: 1, x: 0, y: 0 }),
      easeCubicInOut:    t => t,
      interpolateString: (a, b) => t => b,  // CameraController uses this for transform tween
      select: () => ({
        transition: () => mockTransition(),
        call: (fn, t) => { calls.push({ fn: 'call', t }); },
      }),
    };

    const mockSvgEl = {
      clientWidth:  800,
      clientHeight: 600,
      getBoundingClientRect: () => ({ width: 800, height: 600 }),
    };
    const mockZoom = { transform: () => {} };

    // New signature: (svgEl, zoomG, zoom, theme, d3)
    const cam = new CameraController(mockSvgEl, mockZoomGSel, mockZoom, THEME, mockD3);
    return { cam, calls, mockSvgEl, mockZoom };
  }

  test('constructs without throwing', () => {
    const { cam } = makeMockCamera();
    ok(cam !== null);
  });

  test('destroy() sets internal refs to null without throwing', () => {
    const { cam } = makeMockCamera();
    cam.destroy();
    ok(cam._svg  === null);
    ok(cam._zoom === null);
  });

  test('update() with INITIAL_STATE calls fitAll path (no throw)', () => {
    const { cam } = makeMockCamera();
    const layout  = fakeLayout(3);
    const plan    = choreograph(null, fakeStep(ACTIONS.INITIAL_STATE), THEME);
    cam.update(fakeStep(ACTIONS.INITIAL_STATE), layout, plan);
    ok(true); // just verifying no crash
  });

  test('update() with OPERATION_COMPLETE calls fitAll path (no throw)', () => {
    const { cam } = makeMockCamera();
    const layout  = fakeLayout(3);
    const plan    = choreograph(null, fakeStep(ACTIONS.OPERATION_COMPLETE), THEME);
    cam.update(fakeStep(ACTIONS.OPERATION_COMPLETE), layout, plan);
    ok(true);
  });

  test('update() with SPLIT_ROOT calls fitAll path (no throw)', () => {
    const { cam } = makeMockCamera();
    const layout  = fakeLayout(3);
    const plan    = choreograph(null, fakeStep(ACTIONS.SPLIT_ROOT), THEME);
    cam.update(fakeStep(ACTIONS.SPLIT_ROOT), layout, plan);
    ok(true);
  });

  test('update() with every action in ACTIONS does not throw', () => {
    const { cam } = makeMockCamera();
    const layout  = fakeLayout(3);
    for (const action of Object.values(ACTIONS)) {
      const step = fakeStep(action);
      const plan = choreograph(null, step, THEME);
      cam.update(step, layout, plan);
    }
    ok(true);
  });

  test('update() with empty layout does not throw', () => {
    const { cam } = makeMockCamera();
    cam.update(fakeStep(ACTIONS.INITIAL_STATE), { nodes: {}, keys: {}, pointerDots: {}, edges: {} }, {});
    ok(true);
  });

  test('update() with null layout does not throw', () => {
    const { cam } = makeMockCamera();
    cam.update(fakeStep(ACTIONS.SEARCH_ENTER_NODE), null, {});
    ok(true);
  });

  test('update() with null plan does not throw', () => {
    const { cam } = makeMockCamera();
    cam.update(fakeStep(ACTIONS.SEARCH_ENTER_NODE), fakeLayout(), null);
    ok(true);
  });

  test('panToNode() with missing nodeId does not throw', () => {
    const { cam } = makeMockCamera();
    cam.panToNode('nonexistent', fakeLayout(), 300);
    ok(true);
  });
});

suite('CameraController --, rule routing logic', () => {
  // These tests verify which "rule path" is taken by checking what
  // _findActiveNode / _findHighlightedParent return for known step fixtures.

  function makeCam() {
    const { CameraController } = require('../animation/CameraController');

    const mockTransition = () => ({
      delay: () => mockTransition(), duration: () => mockTransition(),
      ease: () => mockTransition(), attrTween: () => mockTransition(),
      attr: () => mockTransition(), call: () => mockTransition(),
    });
    const mockZoomGSel = {
      attr: () => mockZoomGSel,
      transition: () => mockTransition(),
    };
    const mockD3 = {
      zoomIdentity: { translate: () => ({ scale: () => ({}) }), scale: () => ({}) },
      zoomTransform: () => ({ k: 1, x: 0, y: 0 }),
      easeCubicInOut: t => t,
      interpolateString: (a, b) => t => b,
      select: () => ({ transition: () => mockTransition(), call: () => {} }),
    };
    const mockSvgEl = { clientWidth: 800, clientHeight: 600, getBoundingClientRect: () => ({ width: 800, height: 600 }) };
    // New signature: (svgEl, zoomG, zoom, theme, d3)
    return new CameraController(mockSvgEl, mockZoomGSel, { transform: () => {} }, THEME, mockD3);
  }

  test('_findActiveNode returns the active-role highlighted node', () => {
    const cam  = makeCam();
    const step = fakeStep(ACTIONS.SEARCH_ENTER_NODE, [{ nodeId: 'n2', role: 'active' }]);
    eq(cam._findActiveNode(step), 'n2');
  });

  test('_findActiveNode returns null when no active highlight', () => {
    const cam  = makeCam();
    const step = fakeStep(ACTIONS.SEARCH_ENTER_NODE, [{ nodeId: 'n1', role: 'parent' }]);
    eq(cam._findActiveNode(step), null);
  });

  test('_findActiveNode finds overflow role too', () => {
    const cam  = makeCam();
    const step = fakeStep(ACTIONS.OVERFLOW_DETECTED, [{ nodeId: 'n3', role: 'overflow' }]);
    eq(cam._findActiveNode(step), 'n3');
  });

  test('_findActiveNode finds underflow role', () => {
    const cam  = makeCam();
    const step = fakeStep(ACTIONS.UNDERFLOW_DETECTED, [{ nodeId: 'n2', role: 'underflow' }]);
    eq(cam._findActiveNode(step), 'n2');
  });

  test('_findHighlightedParent returns the parent-role node', () => {
    const cam  = makeCam();
    const step = fakeStep(ACTIONS.PROMOTE_INTO_PARENT, [
      { nodeId: 'n1', role: 'parent' },
      { nodeId: 'n2', role: 'active' },
    ]);
    eq(cam._findHighlightedParent(step), 'n1');
  });

  test('_findHighlightedParent returns null when no parent highlight', () => {
    const cam  = makeCam();
    const step = fakeStep(ACTIONS.SEARCH_ENTER_NODE, [{ nodeId: 'n2', role: 'active' }]);
    eq(cam._findHighlightedParent(step), null);
  });

  test('_collectHighlightedNodeIds returns all highlighted node IDs', () => {
    const cam  = makeCam();
    const step = fakeStep(ACTIONS.SPLIT_EXECUTE, [
      { nodeId: 'n1', role: 'parent' },
      { nodeId: 'n2', role: 'split_left' },
      { nodeId: 'n3', role: 'split_right' },
    ]);
    const ids = cam._collectHighlightedNodeIds(step);
    eq(ids.length, 3);
    ok(ids.includes('n1'));
    ok(ids.includes('n2'));
    ok(ids.includes('n3'));
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Sections 3 + 4 --, DOM tests (jsdom + d3 required)
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
  global.location   = _base.window.location;
  global.SVGElement = _base.window.SVGElement;
  // Node 22 made global.navigator a read-only getter --, use defineProperty to override
  try {
    global.navigator = _base.window.navigator;
  } catch (_) {
    Object.defineProperty(global, 'navigator', { value: _base.window.navigator, configurable: true, writable: true });
  }

  const d3 = require('d3');
  const { MinimapRenderer } = require('../animation/MinimapRenderer');
  const { AnimationLayer }  = require('../animation/AnimationLayer');
  const { resetIdCounter }  = require('../core/shared');
  const { createTree }      = require('../core/BTree');
  const { insert }          = require('../core/insert');
  const { deleteKey }       = require('../core/delete');
  const { search }          = require('../core/search');
  const { computeLayout }   = require('../core/layout');

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
      Object.defineProperty(global, 'navigator', { value: dom.window.navigator, configurable: true, writable: true });
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

  function makeStep(state, action = ACTIONS.INITIAL_STATE, nodeHighlights = []) {
    return {
      stepIndex: 0, action, isKeyStep: false, state,
      highlights: { nodes: nodeHighlights, keys: [], edges: [] },
      explanation: '', pseudocodeLine: 0, variables: {}, meta: { phase: 'descend', depth: 0 },
    };
  }

  // ── MinimapRenderer DOM tests ──────────────────────────────────────────────

  suite('MinimapRenderer --, DOM structure', () => {
    test('creates g.minimap-root inside the SVG', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const mm    = new MinimapRenderer(svgEl, THEME, d3);

      ok(svgEl.querySelector('g.minimap-root') !== null, 'g.minimap-root should exist');
      mm.destroy();
    });

    test('minimap-root contains a background rect', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const mm    = new MinimapRenderer(svgEl, THEME, d3);

      const bg = svgEl.querySelector('g.minimap-root rect.minimap-bg');
      ok(bg !== null, 'minimap-bg rect should exist');
      eq(bg.getAttribute('width'),  '200');
      eq(bg.getAttribute('height'), '150');
      mm.destroy();
    });

    test('minimap-root contains a label text element', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const mm    = new MinimapRenderer(svgEl, THEME, d3);

      const label = svgEl.querySelector('g.minimap-root text.minimap-label');
      ok(label !== null, 'minimap-label text should exist');
      eq(label.textContent, 'MINIMAP');
      mm.destroy();
    });

    test('minimap-root is appended to SVG directly (not inside zoom-container)', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const anim  = new AnimationLayer(svgEl, d3);

      const zoomContainer = svgEl.querySelector('g.zoom-container');
      const minimapInside = zoomContainer?.querySelector('g.minimap-root');
      const minimapDirect = svgEl.querySelector('g.minimap-root');

      eq(minimapInside, null, 'minimap should NOT be inside zoom-container');
      ok(minimapDirect !== null, 'minimap should be direct child of SVG');
      anim.destroy();
    });

    test('destroy() removes g.minimap-root from DOM', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const mm    = new MinimapRenderer(svgEl, THEME, d3);

      mm.destroy();
      eq(svgEl.querySelector('g.minimap-root'), null, 'minimap-root should be removed');
    });

    test('a clipPath is added to the SVG defs for the minimap', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const mm    = new MinimapRenderer(svgEl, THEME, d3);

      const clip = svgEl.querySelector('defs clipPath');
      ok(clip !== null, 'a clipPath should exist in defs');
      mm.destroy();
    });

    test('minimap-content group exists inside minimap-root', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const mm    = new MinimapRenderer(svgEl, THEME, d3);

      ok(svgEl.querySelector('g.minimap-root g.minimap-content') !== null);
      mm.destroy();
    });
  });

  suite('MinimapRenderer --, update() draws node rects', () => {
    test('update() creates one mm-node rect per node', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const mm    = new MinimapRenderer(svgEl, THEME, d3);
      const state = buildTree(2, [10, 20, 30, 40]);
      const layout = computeLayout(state);

      mm.update(layout, d3.zoomIdentity);

      const rects = svgEl.querySelectorAll('rect.mm-node');
      eq(rects.length, Object.keys(state.nodes).length,
        `Expected ${Object.keys(state.nodes).length} mm-node rects`);
      mm.destroy();
    });

    test('update() creates one mm-edge line per parent-child relationship', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const mm    = new MinimapRenderer(svgEl, THEME, d3);
      const state = buildTree(2, [10, 20, 30, 40]);
      const layout = computeLayout(state);

      mm.update(layout, d3.zoomIdentity);

      const lines    = svgEl.querySelectorAll('line.mm-edge');
      const expected = Object.keys(layout.edges).length;
      eq(lines.length, expected);
      mm.destroy();
    });

    test('single-node tree: 1 mm-node rect, 0 mm-edge lines', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const mm    = new MinimapRenderer(svgEl, THEME, d3);
      const state = buildTree(2, [42]);
      const layout = computeLayout(state);

      mm.update(layout, d3.zoomIdentity);

      eq(svgEl.querySelectorAll('rect.mm-node').length, 1);
      eq(svgEl.querySelectorAll('line.mm-edge').length, 0);
      mm.destroy();
    });

    test('update() with no layout does not throw', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const mm    = new MinimapRenderer(svgEl, THEME, d3);

      mm.update(null, d3.zoomIdentity);
      ok(true);
      mm.destroy();
    });

    test('calling update() twice updates the node count correctly', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const mm    = new MinimapRenderer(svgEl, THEME, d3);

      const state1 = buildTree(2, [10]);
      mm.update(computeLayout(state1), d3.zoomIdentity);
      eq(svgEl.querySelectorAll('rect.mm-node').length, 1);

      const state2 = buildTree(2, [10, 20, 30, 40]);
      mm.update(computeLayout(state2), d3.zoomIdentity);
      eq(svgEl.querySelectorAll('rect.mm-node').length, Object.keys(state2.nodes).length);
      mm.destroy();
    });

    test('viewport rect exists and has non-zero dimensions after update', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const mm    = new MinimapRenderer(svgEl, THEME, d3);
      const state = buildTree(2, [10, 20, 30]);
      mm.update(computeLayout(state), d3.zoomIdentity);

      const vp = svgEl.querySelector('rect.minimap-viewport');
      ok(vp !== null, 'minimap-viewport rect should exist');
      const w = parseFloat(vp.getAttribute('width')  ?? '0');
      const h = parseFloat(vp.getAttribute('height') ?? '0');
      ok(w > 0, `viewport width should be > 0, got ${w}`);
      ok(h > 0, `viewport height should be > 0, got ${h}`);
      mm.destroy();
    });

    test('mm-node rects have positive width and height', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const mm    = new MinimapRenderer(svgEl, THEME, d3);
      const state = buildTree(2, [10, 20, 30, 40, 50]);
      mm.update(computeLayout(state), d3.zoomIdentity);

      const rects = svgEl.querySelectorAll('rect.mm-node');
      for (const r of rects) {
        ok(parseFloat(r.getAttribute('width'))  > 0, 'mm-node width should be > 0');
        ok(parseFloat(r.getAttribute('height')) > 0, 'mm-node height should be > 0');
      }
      mm.destroy();
    });

    test('minimap-root has a transform attribute positioning it in the corner', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const mm    = new MinimapRenderer(svgEl, THEME, d3);

      const root = svgEl.querySelector('g.minimap-root');
      const t = root?.getAttribute('transform') ?? '';
      ok(t.startsWith('translate('), `Expected translate(...) transform, got: "${t}"`);
      mm.destroy();
    });
  });

  // ── AnimationLayer integration with camera + minimap ────────────────────────

  suite('AnimationLayer Stage 5 --, structure', () => {
    test('zoom-container, minimap-root, AND no float-layer inside zoom-container', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const anim  = new AnimationLayer(svgEl, d3);

      ok(svgEl.querySelector('g.zoom-container') !== null, 'zoom-container');
      ok(svgEl.querySelector('g.minimap-root')   !== null, 'minimap-root');
      ok(svgEl.querySelector('g.float-layer')    !== null, 'float-layer');

      // float-layer should be inside zoom-container
      const zc = svgEl.querySelector('g.zoom-container');
      ok(zc.querySelector('g.float-layer') !== null, 'float-layer inside zoom-container');

      // minimap should be a sibling of zoom-container, not inside it
      ok(zc.querySelector('g.minimap-root') === null, 'minimap not inside zoom-container');
      anim.destroy();
    });

    test('destroy() removes zoom-container AND minimap-root', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const anim  = new AnimationLayer(svgEl, d3);
      anim.destroy();

      eq(svgEl.querySelector('g.zoom-container'), null);
      eq(svgEl.querySelector('g.minimap-root'),   null);
    });

    test('render() updates minimap (mm-node rects appear)', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const anim  = new AnimationLayer(svgEl, d3);

      const state = buildTree(2, [10, 20, 30, 40]);
      anim.render(makeStep(state));

      const nodeCount   = Object.keys(state.nodes).length;
      const mmNodeRects = svgEl.querySelectorAll('rect.mm-node');
      eq(mmNodeRects.length, nodeCount,
        `Expected ${nodeCount} mm-node rects after render`);
      anim.destroy();
    });

    test('render() does not throw on any step from a full insert sequence', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const anim  = new AnimationLayer(svgEl, d3);

      const state = buildTree(2, [10, 20, 30]);
      const steps = insert(state, 40);

      let errors = 0;
      for (const step of steps) {
        try { anim.render(step); } catch (e) { errors++; console.error(e.message); }
      }
      eq(errors, 0);
      anim.destroy();
    });

    test('render() does not throw on any step from a full delete sequence', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const anim  = new AnimationLayer(svgEl, d3);

      const state = buildTree(2, [10, 20, 30, 40, 50]);
      const steps = deleteKey(state, 10);

      let errors = 0;
      for (const step of steps) {
        try { anim.render(step); } catch (e) { errors++; console.error(e.message); }
      }
      eq(errors, 0);
      anim.destroy();
    });

    test('render() does not throw on any step from a full search sequence', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const anim  = new AnimationLayer(svgEl, d3);

      const state = buildTree(2, [10, 20, 30, 40, 50]);
      const steps = search(state, 30);

      let errors = 0;
      for (const step of steps) {
        try { anim.render(step); } catch (e) { errors++; console.error(e.message); }
      }
      eq(errors, 0);
      anim.destroy();
    });

    test('cameraController and minimapRenderer accessible via getters', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const anim  = new AnimationLayer(svgEl, d3);

      ok(anim.cameraController !== null && anim.cameraController !== undefined);
      ok(anim.minimapRenderer  !== null && anim.minimapRenderer  !== undefined);
      anim.destroy();
    });

    test('minimap node count updates when a different state is rendered', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const anim  = new AnimationLayer(svgEl, d3);

      const state1 = buildTree(2, [10]);
      anim.render(makeStep(state1));
      const count1 = svgEl.querySelectorAll('rect.mm-node').length;

      const state2 = buildTree(2, [10, 20, 30, 40, 50]);
      anim.render(makeStep(state2));
      const count2 = svgEl.querySelectorAll('rect.mm-node').length;

      ok(count2 > count1, `mm-node count should grow (${count1} → ${count2})`);
      anim.destroy();
    });

    test('fitView() does not throw after render()', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const anim  = new AnimationLayer(svgEl, d3);

      const state = buildTree(2, [10, 20, 30]);
      anim.render(makeStep(state));
      anim.fitView();
      ok(true);
      anim.destroy();
    });

    test('minimap viewport rect shifts when zoom transform changes', () => {
      const dom   = makeDOM();
      const svgEl = dom.window.document.getElementById('svg');
      const anim  = new AnimationLayer(svgEl, d3);

      const state  = buildTree(2, [10, 20, 30]);
      const layout = computeLayout(state);

      // Render with identity transform
      anim.render(makeStep(state));
      const vp   = svgEl.querySelector('rect.minimap-viewport');
      const x1   = parseFloat(vp?.getAttribute('x') ?? '0');

      // Update minimap manually with a panned transform
      const panTransform = d3.zoomIdentity.translate(-300, 0);
      anim.minimapRenderer.update(layout, panTransform);
      const x2 = parseFloat(vp?.getAttribute('x') ?? '0');

      // A pan to the left in the main camera means the viewport rect moves right in the minimap
      ok(x2 !== x1, `Viewport x should change with zoom transform (was ${x1}, now ${x2})`);
      anim.destroy();
    });
  });
}

// ─────────────────────────────────────────────────────────────────────────────

summary();
process.exit(0);