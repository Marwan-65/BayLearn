
// el file da byet2aked en el enter w exit animations bta3t el edges betetfire sah w consistent ma3 the step object w index, w enna el destroy method byet2aked enha btetnada sah w consistent ma3a the destroyed state (e.g. after destroy is called, no further events should fire and all methods should be no-ops). Kaman byet2aked en el styles eli betetapply lel edges ma3moola b sah w consistent ma3 el theme object w el role-based styling defined feh. W enna el highlights eli betetapply lel edges fe kol step b sah w consistent ma3 el step.highlights.edges array w el mapping ela layout edges.
class EdgeRenderer {
  // bta5od parentG (D3 selection of a <g> element to render edges into), theme (for styling), w d3 instance (for transitions and easing).
  constructor(parentG, theme, d3) {
    // Edges go BELOW nodes,  h7sy so insert as first child
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
      .attr('x2', d => d.fromDot.x) // start collapsed 87sy at source dot
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
      // ersem el line da mn el source l destination, w estakhdem dash-draw effect
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


function _buildEdgeRoleMap(step, layout) { // el function di betbni map mn edge keys (el keys eli mawgoda fe layout.edges) lel roles eli hatetapply lehom based 3la el step.highlights.edges array. El highlights array feh objects b two properties: fromId w toId (node IDs), w role (string). El layout.edges keys mawgoda fe form "parentId→childId". Fa el function di btet2aked enha btetmatch sah w consistent ma3 el highlights w el layout edges, w btetbuild map sah keda. El role-based styling ba3d keda hatetapply fe render() bas based 3la el roles feh.
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