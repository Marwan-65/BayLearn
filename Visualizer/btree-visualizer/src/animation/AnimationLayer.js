// AnimationLayer.js
//
// Top-level animation orchestrator. Owns the SVG element, constructs all
// sub-renderers, and is the only module that calls the Choreographer.
//
// Stage 5 additions over Stage 4:
//   - CameraController instantiated and called after every render
//   - MinimapRenderer instantiated and updated after every render
//   - Minimap click-to-teleport wired through CameraController.panToNode()
//   - Current zoom transform tracked and passed to MinimapRenderer
//
// SVG layer order (bottom → top):
//   1. <g class="edges-layer">   EdgeRenderer
//   2. <g class="nodes-layer">   NodeRenderer
//   3. <g class="float-layer">   FloatLayer
//   (minimap-root appended directly to <svg>, outside the zoom-container)

const { computeLayout }      = require('../core/layout');
const { NodeRenderer }       = require('./NodeRenderer');
const { EdgeRenderer }       = require('./EdgeRenderer');
const { FloatLayer }         = require('./FloatLayer');
const { CameraController }   = require('./CameraController');
const { MinimapRenderer }    = require('./MinimapRenderer');
const { createTheme }        = require('./ThemeModule');
const { choreograph }        = require('../choreography/Choreographer');
const { ACTIONS }            = require('../core/constants');
const { FocusController }    = require('./FocusController');

class AnimationLayer {
  /**
   * @param {SVGElement} svgEl           - raw <svg> DOM element
   * @param {object}     d3              - d3 namespace (injected for testability)
   * @param {object}     themeOverrides  - optional partial theme
   */
  constructor(svgEl, d3, themeOverrides = {}) {
    this._d3    = d3;
    this._theme = createTheme(themeOverrides);
    this._svg   = d3.select(svgEl);
    this._svgEl = svgEl;

    // Zoom behaviour --, shared between AnimationLayer (user drag) and CameraController (programmatic)
    this._zoom = d3.zoom()
      .scaleExtent([0.08, 5])
      .on('zoom', event => {
        this._zoomG.attr('transform', event.transform);
        this._currentTransform = event.transform;
        // Keep camera controller's internal state in sync with manual pan/zoom
        if (this._cameraController) this._cameraController.syncTransform(event.transform);
        // Keep minimap viewport rect in sync when user pans manually
        if (this._minimapRenderer && this._lastLayout) {
          this._minimapRenderer.update(this._lastLayout, event.transform);
        }
      });

    this._svg.call(this._zoom);
    this._currentTransform = d3.zoomIdentity;

    // Zoom container --, all tree content lives here
    this._zoomG = this._svg.append('g').attr('class', 'zoom-container');

    // Sub-renderers in z-order (edges first = behind nodes = behind float keys)
    this._edgeRenderer = new EdgeRenderer(this._zoomG, this._theme, d3);
    this._nodeRenderer = new NodeRenderer(this._zoomG, this._theme, d3);
    this._floatLayer   = new FloatLayer(this._zoomG, this._theme, d3);

    // Focus controller --, dims non-highlighted nodes after every render
    // Must be created after nodeRenderer so we can grab the nodes-layer g
    this._focusController = new FocusController(
      this._zoomG.select('g.nodes-layer'),
      this._theme,
      d3
    );

    // Camera controller --, programmatic zoom/pan, reads the same zoom behaviour
    this._cameraController = new CameraController(svgEl, this._zoomG, this._zoom, this._theme, d3);

    // Minimap --, appended directly to the SVG so it stays fixed in the corner
    this._minimapRenderer = new MinimapRenderer(
      svgEl,
      this._theme,
      d3,
      // Click-to-teleport callback: pan the main camera to the clicked node
      (nodeId, _layoutX, _layoutY) => {
        if (this._lastLayout) {
          this._cameraController.panToNode(nodeId, this._lastLayout, 500);
        }
      }
    );

    this._lastLayout = null;
    this._lastState  = null;
    this._prevStep   = null;
  }

  // ── Public API ──────────────────────────────────────────────────────────────

  /**
   * Render one step. Computes layout, delegates to all sub-renderers,
   * fires float arcs, updates camera and minimap.
   *
   * @param {Step}   step          - current step from PlaybackController
   * @param {object} [planOverride] - bypass Choreographer (used in tests)
   */
  render(step, planOverride) {
    this._floatLayer.clear();

    const layout = computeLayout(step.state, _layoutTheme(this._theme));
    this._lastLayout = layout;
    this._lastState  = step.state;

    const plan = planOverride ?? choreograph(this._prevStep, step, this._theme);

    this._edgeRenderer.render(step, layout, plan);
    this._nodeRenderer.render(step, layout, plan);
    this._launchFloatArcs(step, layout, plan);

    // Focus must run after NodeRenderer so the g.node-group elements exist
    this._focusController.update(step, plan);

    // Camera moves after renderers so it knows the new layout
    this._cameraController.update(step, layout, plan);

    // Minimap redraws every frame --, it's lightweight (just rects + lines)
    this._minimapRenderer.update(layout, this._currentTransform);

    this._prevStep = step;
  }

  /**
   * Zoom to fit the entire tree with padding. Delegates to CameraController.
   * @param {BTreeState} [state] - uses lastState if omitted
   */
  fitView(state) {
    const theState = state ?? this._lastState;
    if (!theState) return;

    const layout = state
      ? computeLayout(state, _layoutTheme(this._theme))
      : this._lastLayout;
    if (!layout) return;

    this._cameraController.fitAll(layout, this._theme.CAMERA_FIT, 0);
  }

  /** Tear down everything --, removes SVG content and zoom listener. */
  destroy() {
    this._floatLayer.destroy();
    this._minimapRenderer.destroy();
    this._cameraController.destroy();
    this._focusController.destroy();
    this._svg.on('.zoom', null);
    this._zoomG.remove();
  }

  // Exposed for testing
  get lastLayout()  { return this._lastLayout; }
  get cameraController()  { return this._cameraController; }
  get minimapRenderer()   { return this._minimapRenderer; }
  get focusController()   { return this._focusController; }

  // ── Float arc launcher (unchanged from Stage 4) ────────────────────────────

  _launchFloatArcs(step, layout, plan) {
    const action = step.action;

    if (action === ACTIONS.PROMOTE_KEY)           this._floatPromoteKey(step, layout, plan);
    if (action === ACTIONS.MERGE_PULL_SEPARATOR)  this._floatSeparatorFall(step, layout, plan);
    if (action === ACTIONS.MERGE_ABSORB_KEYS)     this._floatMergeAbsorb(step, layout, plan);
    if (action === ACTIONS.BORROW_LEFT_ROTATE ||
        action === ACTIONS.BORROW_RIGHT_ROTATE)   this._floatBorrowRotate(step, layout, plan);
  }

  _floatPromoteKey(step, layout, plan) {
    const { highlights, state } = step;
    const theme = this._theme;

    const promotingKey = highlights.keys?.find(h => h.role === 'promoting');
    if (!promotingKey) return;
    const { nodeId, keyIndex } = promotingKey;
    const keyValue = state.nodes[nodeId]?.keys[keyIndex];
    if (keyValue === undefined) return;

    const fromSlot = layout.keys[nodeId]?.[keyIndex];
    if (!fromSlot) return;
    const parentId  = state.nodes[nodeId]?.parentId;
    if (!parentId) return;
    const parentNode = state.nodes[parentId];
    const landingIdx = parentNode?.keys.indexOf(keyValue) ?? 0;
    const toSlot     = layout.keys[parentId]?.[landingIdx] ?? layout.nodes[parentId];

    this._floatLayer.animateArc({
      keyValue,
      from:       { x: fromSlot.x + theme.SLOT_WIDTH / 2, y: fromSlot.y + theme.SLOT_HEIGHT / 2 },
      to:         { x: (toSlot.x ?? layout.nodes[parentId]?.x) + theme.SLOT_WIDTH / 2,
                    y: (toSlot.y ?? layout.nodes[parentId]?.y) + theme.SLOT_HEIGHT / 2 },
      delay:      plan.keyMove?.delay    ?? 0,
      duration:   plan.keyMove?.duration ?? 600,
      apexOffset: 80,
      fill:       theme.GOLD_LIGHT,
      bgFill:     theme.GOLD_BG,
      scaleUp:    true,
    });
  }

  _floatSeparatorFall(step, layout, plan) {
    const { highlights, state } = step;
    const theme = this._theme;

    const separatorKey = highlights.keys?.find(h => h.role === 'separator');
    if (!separatorKey) return;
    const { nodeId: parentId, keyIndex } = separatorKey;
    const keyValue  = state.nodes[parentId]?.keys[keyIndex];
    if (keyValue === undefined) return;
    const fromSlot  = layout.keys[parentId]?.[keyIndex];
    if (!fromSlot) return;
    const mergeTarget = highlights.nodes?.find(h => h.role === 'merge_target');
    if (!mergeTarget) return;
    const targetNode  = layout.nodes[mergeTarget.nodeId];
    if (!targetNode) return;

    this._floatLayer.animateArc({
      keyValue,
      from:       { x: fromSlot.x + theme.SLOT_WIDTH / 2, y: fromSlot.y + theme.SLOT_HEIGHT / 2 },
      to:         { x: targetNode.x, y: targetNode.y + theme.SLOT_HEIGHT / 2 },
      delay:      plan.keyMove?.delay    ?? 0,
      duration:   plan.keyMove?.duration ?? 400,
      apexOffset: -30,
      fill:       theme.TEXT,
      bgFill:     theme.BG_SURFACE3,
      bounce:     true,
    });
  }

  _floatMergeAbsorb(step, layout, plan) {
    const { highlights, state } = step;
    const theme = this._theme;

    const mergeSource = highlights.nodes?.find(h => h.role === 'merge_source');
    const mergeTarget = highlights.nodes?.find(h => h.role === 'merge_target');
    if (!mergeSource || !mergeTarget) return;

    const sourceNode   = state.nodes[mergeSource.nodeId];
    const targetLayout = layout.nodes[mergeTarget.nodeId];
    if (!sourceNode || !targetLayout) return;

    const sourceSlots = layout.keys[mergeSource.nodeId] ?? [];
    const baseDelay   = plan.keyMove?.delay ?? 0;
    const keyDur      = plan.keyMove?.duration ?? theme.MERGE_KEY_FLY;

    sourceNode.keys.forEach((keyValue, i) => {
      const fromSlot = sourceSlots[i];
      if (!fromSlot) return;
      this._floatLayer.animateArc({
        keyValue,
        from:       { x: fromSlot.x + theme.SLOT_WIDTH / 2, y: fromSlot.y + theme.SLOT_HEIGHT / 2 },
        to:         { x: targetLayout.x, y: targetLayout.y + theme.SLOT_HEIGHT / 2 },
        delay:      baseDelay + i * theme.MERGE_KEY_STAGGER,
        duration:   keyDur,
        apexOffset: 40,
        fill:       theme.TEXT,
        bgFill:     theme.BG_SURFACE3,
        bounce:     true,
      });
    });
  }

  _floatBorrowRotate(step, layout, plan) {
    const { highlights, state, action } = step;
    const theme  = this._theme;
    const isLeft = action === ACTIONS.BORROW_LEFT_ROTATE;

    const siblingRole = isLeft ? 'sibling_left' : 'sibling_right';
    const sibling = highlights.nodes?.find(h => h.role === siblingRole);
    const active  = highlights.nodes?.find(h => h.role === 'active');
    const parent  = highlights.nodes?.find(h => h.role === 'parent');
    if (!sibling || !active || !parent) return;

    const siblingNode  = state.nodes[sibling.nodeId];
    const activeLayout = layout.nodes[active.nodeId];
    const parentLayout = layout.nodes[parent.nodeId];
    if (!siblingNode || !activeLayout || !parentLayout) return;

    const siblingSlots = layout.keys[sibling.nodeId] ?? [];
    const parentSlots  = layout.keys[parent.nodeId]  ?? [];

    const sepHighlight = highlights.keys?.find(h => h.role === 'separator' && h.nodeId === parent.nodeId);
    const sepIdx   = sepHighlight?.keyIndex ?? 0;
    const sepSlot  = parentSlots[sepIdx];
    const sepValue = state.nodes[parent.nodeId]?.keys[sepIdx];

    const baseDelay = plan.keyMove?.delay    ?? (theme.BORROW_HIGHLIGHT_SIBLING + theme.BORROW_HIGHLIGHT_PARENT);
    const arcDur    = plan.keyMove?.duration ?? theme.BORROW_KEY_ARC;

    if (isLeft) {
      const sibIdx   = siblingSlots.length - 1;
      const sibSlot  = siblingSlots[sibIdx];
      const sibValue = siblingNode.keys[sibIdx];
      if (sibSlot && sibValue !== undefined) {
        this._floatLayer.animateArc({
          keyValue: sibValue,
          from:     { x: sibSlot.x + theme.SLOT_WIDTH / 2, y: sibSlot.y + theme.SLOT_HEIGHT / 2 },
          to:       sepSlot
            ? { x: sepSlot.x + theme.SLOT_WIDTH / 2, y: sepSlot.y + theme.SLOT_HEIGHT / 2 }
            : { x: parentLayout.x, y: parentLayout.y + theme.SLOT_HEIGHT / 2 },
          delay: baseDelay, duration: arcDur, apexOffset: 60,
          fill: theme.PURPLE, bgFill: theme.PURPLE_BG, scaleUp: true,
        });
      }
      if (sepSlot && sepValue !== undefined) {
        this._floatLayer.animateArc({
          keyValue: sepValue,
          from:     { x: sepSlot.x + theme.SLOT_WIDTH / 2, y: sepSlot.y + theme.SLOT_HEIGHT / 2 },
          to:       { x: activeLayout.x - activeLayout.width / 2 + theme.NODE_PADDING_X + theme.SLOT_WIDTH / 2,
                      y: activeLayout.y + theme.SLOT_HEIGHT / 2 },
          delay: baseDelay, duration: arcDur, apexOffset: -40,
          fill: theme.GOLD_LIGHT, bgFill: theme.GOLD_BG, bounce: true,
        });
      }
    } else {
      const sibSlot  = siblingSlots[0];
      const sibValue = siblingNode.keys[0];
      if (sibSlot && sibValue !== undefined) {
        this._floatLayer.animateArc({
          keyValue: sibValue,
          from:     { x: sibSlot.x + theme.SLOT_WIDTH / 2, y: sibSlot.y + theme.SLOT_HEIGHT / 2 },
          to:       sepSlot
            ? { x: sepSlot.x + theme.SLOT_WIDTH / 2, y: sepSlot.y + theme.SLOT_HEIGHT / 2 }
            : { x: parentLayout.x, y: parentLayout.y + theme.SLOT_HEIGHT / 2 },
          delay: baseDelay, duration: arcDur, apexOffset: 60,
          fill: theme.PURPLE, bgFill: theme.PURPLE_BG, scaleUp: true,
        });
      }
      if (sepSlot && sepValue !== undefined) {
        this._floatLayer.animateArc({
          keyValue: sepValue,
          from:     { x: sepSlot.x + theme.SLOT_WIDTH / 2, y: sepSlot.y + theme.SLOT_HEIGHT / 2 },
          to:       { x: activeLayout.x + activeLayout.width / 2 - theme.NODE_PADDING_X - theme.SLOT_WIDTH / 2,
                      y: activeLayout.y + theme.SLOT_HEIGHT / 2 },
          delay: baseDelay, duration: arcDur, apexOffset: -40,
          fill: theme.GOLD_LIGHT, bgFill: theme.GOLD_BG, bounce: true,
        });
      }
    }
  }
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function _layoutTheme(theme) {
  return {
    SLOT_WIDTH:         theme.SLOT_WIDTH,
    SLOT_HEIGHT:        theme.SLOT_HEIGHT,
    SLOT_GAP:           theme.SLOT_GAP,
    NODE_PADDING_X:     theme.NODE_PADDING_X,
    NODE_PADDING_Y:     theme.NODE_PADDING_Y,
    LEVEL_SEPARATION:   theme.LEVEL_SEPARATION,
    SIBLING_SEPARATION: theme.SIBLING_SEPARATION,
  };
}

module.exports = { AnimationLayer };