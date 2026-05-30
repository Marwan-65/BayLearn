// FocusController.js
//
// Dims every node that isn't part of the current step to 0.25 opacity and
// restores the ones that are. It creates the "spotlight" effect that keeps
// a student's eye on the relevant parts of the tree.
//
// Important: this runs AFTER NodeRenderer.render() has already placed and
// styled all the node-group elements. FocusController never does its own
// data join --, it just reads the existing DOM elements and tweaks opacity.
// That's what lets it be a completely separate class with no knowledge of
// the node data format.
//
// The root node is never dimmed. Even when it isn't highlighted, it gives
// spatial context, and dimming it would make the tree harder to read.
//
// Zero-duration fast path is preserved for tests throughout, matching the
// same pattern used by NodeRenderer and EdgeRenderer.

const { ACTIONS, NODE_ROLES } = require('../core/constants');

// Actions during which every node should be fully visible. Having anything
// dimmed during these steps would be confusing.
const RESTORE_ALL_ACTIONS = new Set([
  ACTIONS.INITIAL_STATE,
  ACTIONS.OPERATION_COMPLETE,
]);

class FocusController {
  /**
   * @param {d3Selection} nodeLayerG  - the <g class="nodes-layer"> selection
   * @param {object}      theme       - full theme from createTheme()
   * @param {object}      d3          - d3 namespace
   */
  constructor(nodeLayerG, theme, d3) {
    this._layer = nodeLayerG;
    this._theme = theme;
    this._d3    = d3;
  }

  // ── Public API ──────────────────────────────────────────────────────────────

  /**
   * Dim/restore nodes based on the current step's highlights.
   * Called from AnimationLayer.render() right after nodeRenderer.render().
   *
   * @param {Step}      step    - current step
   * @param {object}    plan    - ChoreographyPlan (we use plan.focusChange)
   */
  update(step, plan) {
    if (RESTORE_ALL_ACTIONS.has(step.action)) {
      this.restoreAll(plan?.focusChange?.duration ?? 0);
      return;
    }

    const highlighted = new Set(
      (step.highlights?.nodes ?? []).map(h => h.nodeId)
    );

    // The root always stays fully visible regardless of what's highlighted
    if (step.state?.rootId) {
      highlighted.add(step.state.rootId);
    }

    const duration = plan?.focusChange?.duration ?? 0;
    const delay    = plan?.focusChange?.delay    ?? 0;

    this._layer.selectAll('g.node-group').each(function(nodeId) {
      const el = this._d3 ? this._d3.select(this) : null;
      // NOTE: `this` here is the DOM element, not the class. We need d3 from
      // the outer scope --, but closures inside .each() lose the class `this`.
      // So we do the selection outside and pass via closure below.
    });

    // Use a proper closure-safe approach instead of .each()
    const d3    = this._d3;
    const layer = this._layer;

    layer.selectAll('g.node-group').each(function(nodeId) {
      const targetOpacity = highlighted.has(nodeId) ? 1.0 : 0.25;
      const sel = d3.select(this);

      if (!duration) {
        sel.attr('opacity', targetOpacity);
      } else {
        sel.transition()
          .delay(delay)
          .duration(duration)
          .attr('opacity', targetOpacity);
      }
    });
  }

  /**
   * Restore every node to full opacity immediately (or with a transition).
   * Called directly for INITIAL_STATE and OPERATION_COMPLETE, and can be
   * called externally if you need to reset focus without a step.
   *
   * @param {number} duration  - ms, 0 for synchronous
   */
  restoreAll(duration = 0) {
    const d3    = this._d3;
    const layer = this._layer;

    if (!duration) {
      layer.selectAll('g.node-group').attr('opacity', 1.0);
    } else {
      layer.selectAll('g.node-group')
        .transition()
        .duration(duration)
        .attr('opacity', 1.0);
    }
  }

  /**
   * Null out references. The DOM elements are not touched --, they get cleaned
   * up by NodeRenderer's own exit transitions.
   */
  destroy() {
    this._layer = null;
  }
}

module.exports = { FocusController };
