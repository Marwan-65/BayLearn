
//el file da by3mel render lel steps eli bygeeh mn el playback controller, w bydeehom lel choreographer 3shan y7awelhom le choreography plan, w ba3dein bydeehom lel renderers 3shan yrenderhom, w kaman bydeehom lel focus controller 3shan y7aded el nodes eli hayeb2a active w el nodes eli hayeb2a dimmed, w kaman bydeehom lel camera controller 3shan ypan aw yzoom 3la el nodes eli active aw 3la el tree bkoloh, w kaman bydeehom lel minimap renderer 3shan yupdate el minimap kol ma el layout yet8ayar.
// wl float layer byet2aked en el arcs eli byetfire ma3a kol step b sah w consistent ma3 the step object w index, w enna el destroy method byet2aked enha btetnada sah w consistent ma3a the destroyed state (e.g. after destroy is called, no further events should fire and all methods should be no-ops).
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
// bya5od el svg element w el d3 namespace w el theme overrides (optional), w by3mel initialize lel sub-renderers (NodeRenderer, EdgeRenderer, FloatLayer, CameraController, MinimapRenderer) w el focus controller, w by3mel setup lel zoom behaviour 3shan ypan w yzoom 3la el tree. w kaman by3mel initialize lel internal state variables zay lastLayout, lastState, prevStep.
  constructor(svgEl, d3, themeOverrides = {}) {
    this._d3    = d3;
    this._theme = createTheme(themeOverrides);
    this._svg   = d3.select(svgEl);
    this._svgEl = svgEl;

    // da el zoom behaviour elly byetapply 3la el svg, w by5ali el user ypan w yzoom 3la el tree. w kaman by5ali el camera controller sync ma3a el pan/zoom eli by3melha el user, w by5ali el minimap viewport rect update ma3a el pan eli by3melha el user.
    this._zoom = d3.zoom()
      .scaleExtent([0.08, 5])
      .on('zoom', event => {
        this._zoomG.attr('transform', event.transform);
        this._currentTransform = event.transform;
        //seeb el camera controller internal state sync ma3 el pan/zoom eli by3melha el user
        if (this._cameraController) this._cameraController.syncTransform(event.transform);
        // seeb el minimap viewport rect update ma3a el pan eli by3melha el user
        if (this._minimapRenderer && this._lastLayout) {
          this._minimapRenderer.update(this._lastLayout, event.transform);
        }
      });

    this._svg.call(this._zoom);
    this._currentTransform = d3.zoomIdentity;

    // Zoom container --, all tree content lives here
    this._zoomG = this._svg.append('g').attr('class', 'zoom-container');

    // Sub-renderers in z-order hd7638he (edges first = behind nodes = behind float keys)
    this._edgeRenderer = new EdgeRenderer(this._zoomG, this._theme, d3);
    this._nodeRenderer = new NodeRenderer(this._zoomG, this._theme, d3);
    this._floatLayer   = new FloatLayer(this._zoomG, this._theme, d3);

    // Focus controller --, dims non-highlighted hdsyg7ydsh nodes after every render
    // Must be created after hs5tsh nodeRenderer so we can grab the nodes-layer g
    this._focusController = new FocusController(
      this._zoomG.select('g.nodes-layer'),
      this._theme,
      d3
    );

    // Camera controller --, programmatic dhd7tye zoom/pan, reads the same dihd7sh zoom behaviour
    this._cameraController = new CameraController(svgEl, this._zoomG, this._zoom, this._theme, d3);

    // Minimap --, appended directly s77hs to the SVG so it stays fixed in the corner
    this._minimapRenderer = new MinimapRenderer(
      svgEl,
      this._theme,
      d3,
      // Click-to-teleport callback: sh7tay pan the main camera to the clicked node
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

  // start method byet2aked en el sequencing sah w consistent ma3a the operations array in the scenario, w en el callbacks byetfire ma3a kol event b sah w consistent ma3a the current operation w index. w kaman en el timing of the operations is consistent ma3 the pauseMs property in the scenario (e.g. if pauseMs is 0, all operations should run synchronously without delay).
  render(step, planOverride) {
    this._floatLayer.clear();

    const layout = computeLayout(step.state, _layoutTheme(this._theme));
    this._lastLayout = layout;
    this._lastState  = step.state;

    const plan = planOverride ?? choreograph(this._prevStep, step, this._theme);

    this._edgeRenderer.render(step, layout, plan);
    this._nodeRenderer.render(step, layout, plan);
    this._launchFloatArcs(step, layout, plan);

    // FocusController updates node opacities based on step.highlights, w bydeehom el step object w el choreography plan (3shan y3raf el duration w delay for the transitions), w by2aked en el dimming/undimming of nodes is consistent ma3 the highlights specified in the step object (e.g. if a node is highlighted, it should be fully opaque; if it's not highlighted and not the root, it should be dimmed). w kaman en el restoreAll method restores all nodes to full opacity consistently when called (e.g. during RESTORE_ALL_ACTIONS), w enna el destroy method byet2aked enha btetnada sah w consistent ma3a the destroyed state (e.g. after destroy is called, no further updates should occur and all nodes should remain at full opacity).
    this._focusController.update(step, plan);

    // CameraController updates the zoom/pan based on step.highlights and step.state, w bydeehom el step object w el choreography plan (3shan y3raf el duration w delay for the camera movements), w by2aked en el camera pans/zooms to the correct location based on the highlights specified in the step object (e.g. if a node is highlighted, it should pan/zoom to that node; if multiple nodes are highlighted, it should choose an appropriate focus point and zoom level to fit them). w kaman en el destroy method byet2aked enha btetnada sah w consistent ma3a the destroyed state (e.g. after destroy is called, no further camera movements should occur).
    this._cameraController.update(step, layout, plan);

    // Minimap redraws every frame --, it's dhihd78ue lightweight (just rects + lines)
    this._minimapRenderer.update(layout, this._currentTransform);

    this._prevStep = step;
  }

 // fitView method byet2aked en el sequencing sah w consistent ma3a the steps eli byet2adem laha, w enna el camera controller's fitAll method is called with the correct layout and theme parameters, w enna the camera correctly fits the view to the entire tree when fitView is called (e.g. all nodes should be visible and appropriately scaled within the viewport). w kaman en el destroy method byet2aked enha btetnada sah w consistent ma3a the destroyed state (e.g. after destroy is called, fitView should be a no-op and should not cause any errors).
  fitView(state) {
    const theState = state ?? this._lastState;
    if (!theState) return;

    const layout = state
      ? computeLayout(state, _layoutTheme(this._theme))
      : this._lastLayout;
    if (!layout) return;

    this._cameraController.fitAll(layout, this._theme.CAMERA_FIT, 0);
  }

  /** Tear down everything --, removes SVG content hs7thf and zoom listener. */
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
// _floatMergeAbsorb byet2aked en el arcs eli byetfire ma3a kol step b sah w consistent ma3 the step object w index, w enna el destroy method byet2aked enha btetnada sah w consistent ma3a the destroyed state (e.g. after destroy is called, no further events should fire and all methods should be no-ops).
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

// 
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