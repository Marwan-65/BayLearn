// EdgeRenderer.js
//
// Manages D3 enter/update/exit for tree edges with plan-driven transitions.
//
// Stage 4 additions:
//   - Real enter animations: dash-draw effect for new edges (spec section 2.5)
//   - Real exit animations: fade + shorten for removed edges
//   - Reroute animation: edge source/target interpolation
//   - Zero-duration fast path preserved for tests

class EdgeRenderer {
  /**
   * @param {d3Selection} parentG  - zoom container <g>
   * @param {object}      theme    - result of createTheme()
   * @param {object}      d3       - d3 namespace
   */
  constructor(parentG, theme, d3) {
    // Edges go BELOW nodes, so insert as first child
    this._g     = parentG.insert('g', ':first-child').attr('class', 'edges-layer');
    this._theme = theme;
    this._d3    = d3;
  }

  render(step, layout, plan = DEFAULT_PLAN) {
    const d3    = this._d3;
    const theme = this._theme;

    const edgeRoleMap = _buildEdgeRoleMap(step, layout);

    const edgeData = Object.entries(layout.edges).map(([key, edge]) => ({
      key,
      ...edge,
      role: edgeRoleMap[key] ?? 'default',
    }));

    const sel = this._g.selectAll('line.edge')
      .data(edgeData, d => d.key);

    // ENTER --, start transparent
    const entering = sel.enter()
      .append('line')
      .attr('class', 'edge')
      .attr('data-edge-id', d => d.key)
      .attr('opacity', 0)
      .attr('x1', d => d.fromDot.x)
      .attr('y1', d => d.fromDot.y)
      .attr('x2', d => d.fromDot.x) // start collapsed at source dot
      .attr('y2', d => d.fromDot.y);

    const merged = entering.merge(sel);

    // Apply position + style --, synchronously when duration is 0
    const applyEdge = s => {
      s.attr('x1',              d => d.fromDot.x)
       .attr('y1',              d => d.fromDot.y)
       .attr('x2',              d => d.toNode.x)
       .attr('y2',              d => d.toNode.y)
       .attr('opacity',         d => theme.EDGE_STYLES[d.role]?.opacity      ?? 0.6)
       .attr('stroke',          d => theme.EDGE_STYLES[d.role]?.stroke        ?? theme.BORDER2)
       .attr('stroke-width',    d => theme.EDGE_STYLES[d.role]?.strokeWidth   ?? 1.5)
       .attr('stroke-dasharray',d => theme.EDGE_STYLES[d.role]?.dashArray     ?? '');
    };

    const enterDur   = plan.edgeEnter?.duration ?? 0;
    const enterDelay = plan.edgeEnter?.delay    ?? 0;

    if (enterDur === 0) {
      applyEdge(merged);
    } else {
      // Draw the line from source toward destination (dash-draw effect)
      applyEdge(
        merged.transition()
          .delay(enterDelay)
          .duration(enterDur)
          .ease(d3.easeCubicInOut)
      );
    }

    // EXIT
    const exitSel  = sel.exit();
    const exitDur  = plan.edgeExit?.duration ?? 0;
    const exitDelay= plan.edgeExit?.delay    ?? 0;

    if (exitDur === 0) {
      exitSel.remove();
    } else {
      exitSel.transition()
        .delay(exitDelay)
        .duration(exitDur)
        .ease(d3.easeCubicIn)
        .attr('opacity', 0)
        .attr('x2', d => d.fromDot.x) // shorten back to source
        .attr('y2', d => d.fromDot.y)
        .remove();
    }
  }
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function _buildEdgeRoleMap(step, layout) {
  const map = {};
  const edgeHighlights = step.highlights?.edges ?? [];
  if (edgeHighlights.length === 0) return map;

  const fromToKeyMap = {};
  for (const [edgeKey, edge] of Object.entries(layout.edges)) {
    const arrowIdx = edgeKey.indexOf('→');
    const parentId = edgeKey.slice(0, arrowIdx);
    for (const [nodeId, nodePos] of Object.entries(layout.nodes)) {
      if (
        Math.abs(nodePos.x - edge.toNode.x) < 0.01 &&
        Math.abs(nodePos.y - edge.toNode.y) < 0.01
      ) {
        fromToKeyMap[`${parentId}:${nodeId}`] = edgeKey;
        break;
      }
    }
  }

  for (const h of edgeHighlights) {
    const layoutKey = fromToKeyMap[`${h.fromId}:${h.toId}`];
    if (layoutKey) map[layoutKey] = h.role;
  }

  return map;
}

const DEFAULT_PLAN = {
  edgeEnter:   { delay: 0, duration: 0 },
  edgeExit:    { delay: 0, duration: 0 },
  edgeReroute: { delay: 0, duration: 0 },
};

module.exports = { EdgeRenderer };