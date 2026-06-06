// CameraController.js
//
// Owns the D3 zoom transform for the main SVG canvas and decides where to
// look based on the current step. The Choreographer already tells us HOW LONG
// the camera move should take (via plan.cameraPan.duration) --, we just decide
// WHERE to move.
//
// The 6 rules from spec section 7.2:
//   Rule 1 --, Descent:          Follow the active node down the tree
//   Rule 2 --, Split:            Pull back to show overflowing node + its parent
//   Rule 3 --, Merge:            Pull back to show both siblings + parent separator
//   Rule 4 --, Root split:       Zoom out to show the whole tree before new root
//   Rule 5 --, Operation done:   Fit the entire final tree (600ms)
//   Rule 6 --, Cascade:          Rise one level when fixup propagates upward
//
// IMPLEMENTATION NOTE --, why we don't use d3-zoom transitions:
// D3's zoom transition API (selection.transition().call(zoom.transform, t))
// uses d3-interpolate's SVG transform interpolator, which reads
// svgNode.transform.baseVal.consolidate(). jsdom doesn't implement the
// SVGTransformList API, so this throws in tests. Instead we:
//   1. Animate the zoom container's `transform` attribute using a string-based
//      attrTween (d3.interpolateString) --, works in both jsdom and real browsers.
//   2. Update D3's internal zoom state (node.__zoom) directly so that
//      d3.zoomTransform() stays in sync and manual drag/wheel still works.

const { ACTIONS } = require('../core/constants');

const FOCUS_PADDING      = 120;
const FIT_PADDING_FRAC   = 0.08;
const MAX_FOCUS_SCALE    = 1.8;   // never zoom in past this during node focus
const MAX_DESCENT_SCALE  = 1.5;   // max scale while following descent

class CameraController {
  /**
   * @param {SVGElement}     svgEl   - the raw <svg> DOM element
   * @param {d3Selection}    zoomG   - the <g class="zoom-container"> selection
   * @param {d3ZoomBehaviour} zoom   - the d3.zoom() instance on the svg
   * @param {object}         theme   - full theme from createTheme()
   * @param {object}         d3      - d3 namespace
   */
  constructor(svgEl, zoomG, zoom, theme, d3) {
    this._svgEl = svgEl;
    this._svg   = d3.select(svgEl);
    this._zoomG = zoomG;
    this._zoom  = zoom;
    this._theme = theme;
    this._d3    = d3;

    // Current transform --, kept in sync with the zoom event and our own moves.
    // Starts as zoomIdentity so the first fitAll has a known start point.
    this._current = d3.zoomIdentity;
  }


  /**
   * Called after every AnimationLayer.render(). Picks a camera rule and fires.
   *
   * @param {Step}      step   - current step
   * @param {LayoutMap} layout - computed layout for step.state
   * @param {object}    plan   - ChoreographyPlan (we read plan.cameraPan)
   */
  update(step, layout, plan) {
    if (!layout || Object.keys(layout.nodes ?? {}).length === 0) return;

    const dur   = plan?.cameraPan?.duration ?? 0;
    const delay = plan?.cameraPan?.delay    ?? 0;
    const action = step.action;

    // Rule 5 --, fit all after operation complete or initial render
    if (action === ACTIONS.OPERATION_COMPLETE || action === ACTIONS.INITIAL_STATE) {
      this.fitAll(layout, dur || this._theme.CAMERA_FIT, delay);
      return;
    }

    // Root split: the new empty root shell + old root are the key subjects.
    // Focus on both so the student sees the parent-child relationship form.
    // Don't fitAll here --, fitAll would show an almost-empty canvas with just
    // a tiny shell node.
    if (action === ACTIONS.SPLIT_ROOT) {
      const ids = this._collectHighlightedNodeIds(step);
      if (ids.length > 0) {
        this._focusNodes(ids, layout, dur || this._theme.CAMERA_ZOOM_OUT, delay);
        return;
      }
      this.fitAll(layout, dur || this._theme.CAMERA_ZOOM_OUT, delay);
      return;
    }

    // After the median lands in the parent, fit the whole tree so the student
    // sees the completed split structure.
    if (action === ACTIONS.PROMOTE_INTO_PARENT) {
      this.fitAll(layout, dur || this._theme.CAMERA_FIT, delay);
      return;
    }

    // Rule 6 --, cascade: rise to show parent after merge/shrink
    if (
      action === ACTIONS.ROOT_SHRINK ||
      action === ACTIONS.MERGE_UPDATE_PARENT
    ) {
      const parentId = this._findHighlightedParent(step);
      if (parentId && layout.nodes[parentId]) {
        this._focusNodes([parentId], layout, dur, delay);
        return;
      }
      this.fitAll(layout, dur || this._theme.CAMERA_FIT, delay);
      return;
    }

    // Rule 2 --, show overflowing node + parent simultaneously.
    // SPLIT_EXECUTE: fitAll because highlighted nodes include the orphaned
    // right-half (no layout position) --, _focusNodes would only find the left
    // child and zoom in on just that one node, hiding the root shell above.
    if (
      action === ACTIONS.OVERFLOW_DETECTED ||
      action === ACTIONS.SPLIT_PREPARE
    ) {
      const ids = this._collectHighlightedNodeIds(step)
        .filter(id => layout.nodes[id]);  // only reachable nodes
      if (ids.length > 0) { this._focusNodes(ids, layout, dur, delay); return; }
    }

    if (action === ACTIONS.SPLIT_EXECUTE) {
      // fitAll: shows parent shell + left-child together. Right-half is orphaned
      // so it's not in the layout yet.
      this.fitAll(layout, dur || this._theme.CAMERA_FIT, delay);
      return;
    }

    // Rule 3 --, show siblings + parent separator simultaneously
    if (
      action === ACTIONS.MERGE_PREPARE ||
      action === ACTIONS.FIX_CHOOSE_STRATEGY ||
      action === ACTIONS.UNDERFLOW_DETECTED
    ) {
      const ids = this._collectHighlightedNodeIds(step);
      if (ids.length > 0) { this._focusNodes(ids, layout, dur, delay); return; }
    }

    // Rule 1 --, follow the active node during descent
    if (dur > 0) {
      const activeId = this._findActiveNode(step);
      if (activeId && layout.nodes[activeId]) {
        this._panToKeepVisible(activeId, layout, dur, delay);
        return;
      }
    }
  }

  /**
   * Zoom to fit the entire tree in frame (Rule 5).
   */
  fitAll(layout, duration = 600, delay = 0) {
    if (!layout || Object.keys(layout.nodes).length === 0) return;

    const { w: svgW, h: svgH } = this._svgSize();
    const bbox = _boundingBox(Object.values(layout.nodes));
    if (!bbox) return;

    const padX  = svgW * FIT_PADDING_FRAC;
    const padY  = svgH * FIT_PADDING_FRAC;
    const scale = Math.min(
      (svgW - padX * 2) / (bbox.w || 1),
      (svgH - padY * 2) / (bbox.h || 1),
      3
    );
    const tx = svgW / 2 - scale * bbox.cx;
    const ty = svgH / 2 - scale * bbox.cy;

    this._applyTransform(tx, ty, scale, duration, delay);
  }

  /**
   * Pan to centre a specific node (used by minimap click-to-teleport).
   */
  panToNode(nodeId, layout, duration = 500) {
    const pos = layout?.nodes[nodeId];
    if (!pos) return;

    const { w: svgW, h: svgH } = this._svgSize();
    const scale = this._current.k;
    const tx    = svgW / 2 - scale * pos.x;
    const ty    = svgH / 2 - scale * pos.y;

    this._applyTransform(tx, ty, scale, duration, 0);
  }

  /** Notify the controller that the user has panned/zoomed manually. */
  syncTransform(transform) {
    this._current = transform;
  }

  destroy() {
    this._svg   = null;
    this._zoomG = null;
    this._zoom  = null;
  }


  _focusNodes(nodeIds, layout, duration, delay) {
    const positions = nodeIds.map(id => layout.nodes[id]).filter(Boolean);
    if (positions.length === 0) return;

    const { w: svgW, h: svgH } = this._svgSize();
    const bbox = _boundingBox(positions);
    if (!bbox) return;

    const avail  = { w: svgW - FOCUS_PADDING * 2, h: svgH - FOCUS_PADDING * 2 };
    const scale  = Math.min(avail.w / (bbox.w || 1), avail.h / (bbox.h || 1), MAX_FOCUS_SCALE);
    const tx     = svgW / 2 - scale * bbox.cx;
    const ty     = svgH / 2 - scale * bbox.cy;

    this._applyTransform(tx, ty, scale, duration, delay);
  }

  _panToKeepVisible(nodeId, layout, duration, delay) {
    const pos = layout.nodes[nodeId];
    if (!pos) return;

    const { w: svgW, h: svgH } = this._svgSize();
    const { k, x, y } = this._current;

    // Don't zoom in past MAX_DESCENT_SCALE; zoom out to fit if too zoomed out
    const targetK = Math.min(Math.max(k, 0.5), MAX_DESCENT_SCALE);
    const scaleChanged = Math.abs(targetK - k) > 0.01;

    const screenX = pos.x * targetK + x;
    const screenY = pos.y * targetK + y;

    const m  = FOCUS_PADDING;
    let tx   = scaleChanged ? svgW / 2 - targetK * pos.x : x;
    let ty   = scaleChanged ? svgH / 2 - targetK * pos.y : y;

    if (!scaleChanged) {
      if (screenX < m)             tx += m - screenX;
      if (screenX > svgW - m)     tx -= screenX - (svgW - m);
      if (screenY < m)             ty += m - screenY;
      if (screenY > svgH - m * 2) ty -= screenY - (svgH - m * 2);
    }

    if (Math.abs(tx - x) < 2 && Math.abs(ty - y) < 2 && !scaleChanged) return;
    this._applyTransform(tx, ty, targetK, duration, delay);
  }

  /**
   * Apply a zoom transform, either synchronously (duration=0) or animated.
   *
   * For animation we use string-based attrTween on the zoom container rather
   * than D3's zoom transition API. D3's zoom API reads SVG transform.baseVal
   * which jsdom doesn't implement, causing errors in tests. String interpolation
   * works identically in both environments.
   *
   * D3's internal zoom state (node.__zoom) is updated synchronously so that
   * d3.zoomTransform() stays correct and user-initiated drag/wheel still works.
   */
  _applyTransform(tx, ty, scale, duration, delay) {
    if (!this._zoomG || !this._svg || !this._zoom) return;

    const d3       = this._d3;
    const target   = d3.zoomIdentity.translate(tx, ty).scale(scale);
    const targetStr = `translate(${tx},${ty}) scale(${scale})`;

    // Update D3's internal zoom state so zoomTransform() / drag / wheel are correct.
    // We write directly to node.__zoom (D3's internal storage) to avoid firing
    // the zoom event (which would immediately set the transform attribute and
    // cancel any running transition).
    if (this._svgEl) this._svgEl.__zoom = target;
    this._current = target;

    if (!duration || duration === 0) {
      // Synchronous --, just set the attribute
      this._zoomG.attr('transform', targetStr);
      return;
    }

    // Animated --, use string interpolation on the zoom container element.
    // d3.interpolateString handles "translate(a,b) scale(c)" strings correctly.
    const from    = this._zoomG.attr('transform') || 'translate(0,0) scale(1)';
    const interp  = d3.interpolateString(from, targetStr);

    this._zoomG.transition()
      .delay(delay)
      .duration(duration)
      .ease(d3.easeCubicInOut)
      .attrTween('transform', () => interp);
  }

  _svgSize() {
    const el = this._svgEl;
    return {
      w: el?.clientWidth  || el?.getBoundingClientRect?.().width  || 800,
      h: el?.clientHeight || el?.getBoundingClientRect?.().height || 600,
    };
  }

  _findActiveNode(step) {
    return step.highlights?.nodes?.find(
      h => h.role === 'active' || h.role === 'overflow' || h.role === 'underflow'
    )?.nodeId ?? null;
  }

  _findHighlightedParent(step) {
    return step.highlights?.nodes?.find(h => h.role === 'parent')?.nodeId ?? null;
  }

  _collectHighlightedNodeIds(step) {
    return (step.highlights?.nodes ?? []).map(h => h.nodeId);
  }
}


function _boundingBox(positions) {
  if (!positions || positions.length === 0) return null;

  let minX =  Infinity, maxX = -Infinity;
  let minY =  Infinity, maxY = -Infinity;

  for (const p of positions) {
    const l = p.x - p.width  / 2,  r = p.x + p.width  / 2;
    const t = p.y,                  b = p.y + p.height;
    if (l < minX) minX = l;
    if (r > maxX) maxX = r;
    if (t < minY) minY = t;
    if (b > maxY) maxY = b;
  }

  return { cx: (minX + maxX) / 2, cy: (minY + maxY) / 2, w: maxX - minX, h: maxY - minY };
}

module.exports = { CameraController, _boundingBox };