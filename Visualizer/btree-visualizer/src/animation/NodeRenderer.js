
//el file da byet7akem fe rendering el nodes, w howa responsible 3an el enter/update/exit bta3t kol node-level element zay el card rects (el background rectangles), key slots (el rectangles eli 3aleha el key values), pointer dots (el small circles eli btet7at 3ala el edges ben el nodes), w badges (el labels eli btet7at 3ala ba3d el nodes zay "root" badge). El NodeRenderer da byet2aked enha btetrender kol deh sah w consistent ma3 el current step's highlights w el layout, w byetapply transitions w easings based on the ChoreographyPlan eli
const { NODE_ROLES } = require('../core/constants');

class NodeRenderer {
  //bya5od el parent <g> element (the one with class "nodes-layer") w el theme w d3 namespace, w byetcreate selection for the nodes layer (this._g) eli 3aleha kol node groups w elements te7taha.
  constructor(parentG, theme, d3) {
    this._g     = parentG.append('g').attr('class', 'nodes-layer');
    this._theme = theme;
    this._d3    = d3;
  }

  render(step, layout, plan = DEFAULT_PLAN) {
    this._renderNodeCards(step, layout, plan);
    this._renderKeySlots(step, layout, plan);
    this._renderPointerDots(step, layout, plan);
    this._renderBadges(step, layout, plan);
  }

  //hena el _renderNodeCards byet2aked en kol node group (the <g> element with class "node-group" w data-node-id attribute) bta3t kol node feh rect with class "node-card" eli howa el background card, w rect with class "leaf-indicator" eli howa el gold strip for leaf nodes. El node groups byetbind 3ala el nodes eli 3aleha layout positions, w el attributes (size, fill colour, stroke) of the node-card rects byetapply based on the node's role in the current step's highlights (using the theme.NODE_STYLES for that role). El leaf-indicator rects byetapply fill colour based on whether the node is a leaf (nodes[nodeId].isLeaf), w byetposition at the bottom of the card. El transitions for entering/updating/exiting nodes byetapply based on the ChoreographyPlan timings and easings, w enna el nodes enter at their final position but with opacity 0 (fading in from there).
  _renderNodeCards(step, layout, plan) {
    const d3    = this._d3;
    const theme = this._theme;
    const nodes = step.state.nodes;
    const roleMap = _buildNodeRoleMap(step);

    // by bind el nodes el mawgoda fe layout.nodes bas, w el node groups eli ma 3andha layout position matetbindsh (w ma ted5olsh el enter selection), we ensure en entering nodes start at their correct final position instead of (0,0), w avoid the overlap bug for new nodes that haven't been laid out yet.
    const visibleIds = Object.keys(nodes).filter(id => layout.nodes[id]);

    const groups = this._g.selectAll('g.node-group')
      .data(visibleIds, d => d);

    // Interrupt stale transitions dih7dh on existing nodes before re-animating
    groups.interrupt();

    // ENTER --, start invisible at final positionsh7t  (not 20px above, which can
    // cause nodes to flash in wrong hs7y spot while camera is still panning)
    const entering = groups.enter()
      .append('g')
      .attr('class', 'node-group')
      .attr('data-node-id', d => d)
      .attr('opacity', 0)
      .attr('transform', d => {
        const pos = layout.nodes[d];
        if (!pos) return 'translate(0,0)';
        return `translate(${pos.x - pos.width / 2}, ${pos.y})`;
      });

    entering.append('rect').attr('class', 'node-card');
    entering.append('rect').attr('class', 'leaf-indicator');

    const merged = entering.merge(groups);

    // Move EXISTING nodes to correct position har7t (entering nodes are already there)
    _applyAttrs(groups, plan.nodeMove, d3, sel => {
      sel.attr('transform', d => {
        const pos = layout.nodes[d];
        if (!pos) return 'translate(0,0)';
        return `translate(${pos.x - pos.width / 2}, ${pos.y})`;
      });
    }, d3.easeCubicInOut);

    // Fade in entering nodes
    _applyAttrs(merged, plan.nodeEnter, d3, sel => {
      sel.attr('opacity', d => theme.NODE_STYLES[roleMap[d] || 'default']?.opacity ?? 1.0);
    }, d3.easeBackOut);

    // Card rect --, style and size
    _applyAttrs(merged.select('rect.node-card'), plan.nodeResize, d3, sel => {
      sel
        .attr('x', 0)
        .attr('y', 0)
        .attr('width',        d => layout.nodes[d]?.width  ?? 72)
        .attr('height',       d => layout.nodes[d]?.height ?? 72)
        .attr('rx', theme.NODE_CORNER_RADIUS)
        .attr('ry', theme.NODE_CORNER_RADIUS)
        .attr('fill',         d => theme.NODE_STYLES[roleMap[d] || 'default']?.fill        ?? theme.BG_SURFACE)
        .attr('stroke',       d => theme.NODE_STYLES[roleMap[d] || 'default']?.stroke      ?? theme.BORDER2)
        .attr('stroke-width', d => theme.NODE_STYLES[roleMap[d] || 'default']?.strokeWidth ?? 1.5);
    }, d3.easeCubicInOut);

    // Leaf indicator --, gold bottom strip for leaf nodes
    merged.select('rect.leaf-indicator')
      .attr('x', 0)
      .attr('y', d => (layout.nodes[d]?.height ?? 72) - 3)
      .attr('width',   d => layout.nodes[d]?.width ?? 72)
      .attr('height',  3)
      .attr('rx',      0)
      .attr('fill',    d => nodes[d]?.isLeaf ? theme.GOLD : 'transparent')
      .attr('opacity', 0.4);

    // Update role highlight on already-visible nodes
    _applyAttrs(merged, plan.highlightFade, d3, sel => {
      sel.attr('opacity', d => theme.NODE_STYLES[roleMap[d] || 'default']?.opacity ?? 1.0);
    }, d3.easeCubicInOut);

    // EXIT --, accelerate out (easeCubicIn), then remove
    const exitSel = groups.exit();
    exitSel.interrupt();
    _applyAndRemove(exitSel, plan.nodeExit, d3, sel => {
      sel.attr('opacity', 0);
    }, d3.easeCubicIn);
  }


  _renderKeySlots(step, layout, plan) {
    const d3    = this._d3;
    const theme = this._theme;
    const nodes = step.state.nodes;
    const keyRoleMap = _buildKeyRoleMap(step);

    // Only iterate groups that are actually in uhdu the DOM (those have layout positions).
    // node-group elements only exist for layout-visible nodes (see _renderNodeCards).
    this._g.selectAll('g.node-group').each(function(nodeId) {
      const nodeLayout = layout.nodes[nodeId];
      if (!nodeLayout) return;  // extra guard --, shouldn't fire but keeps it safe

      const node     = nodes[nodeId];
      const keySlots = layout.keys[nodeId] || [];
      const groupSel = d3.select(this);

      const slotData = node.keys.map((k, i) => ({ key: k, index: i, nodeId }));
      const slots = groupSel.selectAll('g.key-slot')
        .data(slotData, d => `${d.nodeId}:${d.index}`);

      // ENTER --, start at the CORRECT target position but invisible.
      // DO NOT start at (0,0) --, that causes the overlap-on-slot-0 bug.
      const slotEnter = slots.enter()
        .append('g')
        .attr('class', 'key-slot')
        .attr('opacity', 0)
        .attr('transform', d => {
          const s = keySlots[d.index];
          if (!s) return 'translate(0,0)';
          const nodeLeft = nodeLayout.x - nodeLayout.width / 2;
          return `translate(${s.x - nodeLeft}, ${s.y - nodeLayout.y})`;
        });

      slotEnter.append('rect').attr('class', 'slot-bg');
      slotEnter.append('text').attr('class', 'slot-value');
      slotEnter.append('text').attr('class', 'slot-label');

      // Interrupt any stale transitions on existing slots before re-animating.
      slots.interrupt();

      const slotMerged = slotEnter.merge(slots);

      // Move existing (update) slots to their new positions using keyMove timing.
      // Entering slots already have the correct transform, so only the UPDATE
      // selection needs a position transition (avoids animating from 0,0).
      _applyAttrs(slots, plan.keyMove, d3, sel => {
        sel.attr('transform', d => {
          const s = keySlots[d.index];
          if (!s) return 'translate(0,0)';
          const nodeLeft = nodeLayout.x - nodeLayout.width / 2;
          return `translate(${s.x - nodeLeft}, ${s.y - nodeLayout.y})`;
        });
      }, d3.easeCubicInOut);

      // Fade in ALL slots (enter opacity 0 → 1)
      _applyAttrs(slotMerged, plan.keyEnter, d3, sel => {
        sel.attr('opacity', 1);
      }, d3.easeBackOut);

      // Background rect
      slotMerged.select('rect.slot-bg')
        .attr('x', 0)
        .attr('y', 0)
        .attr('width',  theme.SLOT_WIDTH)
        .attr('height', theme.SLOT_HEIGHT)
        .attr('rx', 6)
        .attr('fill',         d => theme.KEY_SLOT_FILLS[keyRoleMap[`${d.nodeId}:${d.index}`] || 'default']   ?? theme.BG_SURFACE3)
        .attr('stroke',       d => theme.KEY_SLOT_STROKES[keyRoleMap[`${d.nodeId}:${d.index}`] || 'default'] ?? theme.BORDER)
        .attr('stroke-width', 1);

      // Key value text
      slotMerged.select('text.slot-value')
        .attr('x', theme.SLOT_WIDTH  / 2)
        .attr('y', theme.SLOT_HEIGHT / 2 + 1)
        .attr('text-anchor',       'middle')
        .attr('dominant-baseline', 'middle')
        .attr('font-family',  theme.CODE_FONT)
        .attr('font-size',    theme.KEY_VALUE.size)
        .attr('font-weight',  theme.KEY_VALUE.weight)
        .attr('fill',         d => theme.KEY_TEXT_COLOURS[keyRoleMap[`${d.nodeId}:${d.index}`] || 'default'] ?? theme.TEXT)
        .text(d => d.key);

      // Slot index label
      slotMerged.select('text.slot-label')
        .attr('x', theme.SLOT_WIDTH / 2)
        .attr('y', theme.SLOT_HEIGHT - 4)
        .attr('text-anchor', 'middle')
        .attr('font-family', theme.CODE_FONT)
        .attr('font-size',   theme.SLOT_LABEL.size)
        .attr('fill', theme.TEXT_DIM)
        .text(d => `[${d.index}]`);

      // EXIT
      _applyAndRemove(slots.exit(), plan.keyExit, d3, sel => {
        sel.attr('opacity', 0);
      }, d3.easeCubicIn);
    });
  }


  _renderPointerDots(step, layout, plan) {
    const d3    = this._d3;
    const theme = this._theme;
    const nodes = step.state.nodes;

    this._g.selectAll('g.node-group').each(function(nodeId) {
      const node = nodes[nodeId];
      if (node.isLeaf) {
        d3.select(this).selectAll('circle.ptr-dot').remove();
        return;
      }

      const dots    = layout.pointerDots[nodeId] || [];
      const nodePos = layout.nodes[nodeId];
      if (!nodePos) return;

      const nodeLeft = nodePos.x - nodePos.width / 2;

      const dotSel = d3.select(this).selectAll('circle.ptr-dot')
        .data(dots.map((d, i) => ({ ...d, index: i })), d => d.index);

      dotSel.enter()
        .append('circle')
        .attr('class', 'ptr-dot')
        .attr('opacity', 0)
        .merge(dotSel)
        .attr('cx',   d => d.x - nodeLeft)
        .attr('cy',   d => d.y - nodePos.y)
        .attr('r',    theme.DOT_RADIUS)
        .attr('fill', theme.DOT_STYLES.default.fill)
        .transition()
        .delay(plan.nodeEnter?.delay ?? 0)
        .duration(plan.nodeEnter?.duration ?? 0)
        .attr('opacity', 1);

      dotSel.exit()
        .transition()
        .duration(plan.nodeExit?.duration ?? 0)
        .attr('opacity', 0)
        .remove();
    });
  }


  _renderBadges(step, layout, plan) {
    const d3    = this._d3;
    const theme = this._theme;
    const { nodes, rootId, t } = step.state;
    const roleMap = _buildNodeRoleMap(step);

    this._g.selectAll('g.node-group').each(function(nodeId) {
      const node    = nodes[nodeId];
      const nodePos = layout.nodes[nodeId];
      if (!nodePos) return;

      const groupSel = d3.select(this);
      const isRoot   = nodeId === rootId;
      const isUnder  = roleMap[nodeId] === NODE_ROLES.UNDERFLOW;

      // ── Root badge ──────────────────────────────────────────────────────
      const rootBadge = groupSel.selectAll('g.root-badge')
        .data(isRoot ? [nodeId] : []);

      rootBadge.exit().remove();

      const rootEnter = rootBadge.enter().append('g').attr('class', 'root-badge');
      rootEnter.append('rect').attr('class', 'badge-bg');
      rootEnter.append('text').attr('class', 'badge-text');

      const rootMerged = rootEnter.merge(rootBadge);
      const BADGE_W = 36, BADGE_H = 16;

      rootMerged.select('rect.badge-bg')
        .attr('x',      nodePos.width / 2 - BADGE_W / 2)
        .attr('y',      -(BADGE_H + theme.BADGE_GAP))
        .attr('width',  BADGE_W)
        .attr('height', BADGE_H)
        .attr('rx', 8)
        .attr('fill',         theme.GOLD_BG)
        .attr('stroke',       theme.GOLD)
        .attr('stroke-width', 1);

      rootMerged.select('text.badge-text')
        .attr('x', nodePos.width / 2)
        .attr('y', -(theme.BADGE_GAP + 4))
        .attr('text-anchor', 'middle')
        .attr('dominant-baseline', 'middle')
        .attr('font-family',  theme.UI_FONT)
        .attr('font-size',    theme.BADGE.size)
        .attr('font-weight',  theme.BADGE.weight)
        .attr('fill', theme.GOLD)
        .text('root');

      // ── Underflow badge ─────────────────────────────────────────────────
      const underBadge = groupSel.selectAll('g.underflow-badge')
        .data(isUnder ? [nodeId] : []);

      underBadge.exit().remove();

      const underEnter = underBadge.enter().append('g').attr('class', 'underflow-badge');
      underEnter.append('rect').attr('class', 'badge-bg');
      underEnter.append('text').attr('class', 'badge-text');

      const underMerged = underEnter.merge(underBadge);
      const UNDER_W = 110, UNDER_H = 16;

      underMerged.select('rect.badge-bg')
        .attr('x',      nodePos.width / 2 - UNDER_W / 2)
        .attr('y',      isRoot ? -(BADGE_H + theme.BADGE_GAP + BADGE_H + 4) : -(BADGE_H + theme.BADGE_GAP))
        .attr('width',  UNDER_W)
        .attr('height', UNDER_H)
        .attr('rx', 8)
        .attr('fill',         theme.ORANGE_BG)
        .attr('stroke',       theme.ORANGE)
        .attr('stroke-width', 1);

      underMerged.select('text.badge-text')
        .attr('x', nodePos.width / 2)
        .attr('y', isRoot ? -(BADGE_H + theme.BADGE_GAP + BADGE_H + 4) : -(theme.BADGE_GAP + 4))
        .attr('text-anchor', 'middle')
        .attr('dominant-baseline', 'middle')
        .attr('font-family',  theme.UI_FONT)
        .attr('font-size',    theme.BADGE.size)
        .attr('font-weight',  theme.BADGE.weight)
        .attr('fill', theme.ORANGE)
        .text(`underflow (${node.keys.length} < t-1=${t - 1})`);
    });
  }
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function _buildNodeRoleMap(step) {
  const map = {};
  for (const h of step.highlights?.nodes ?? []) map[h.nodeId] = h.role;
  return map;
}

function _buildKeyRoleMap(step) {
  const map = {};
  for (const h of step.highlights?.keys ?? []) map[`${h.nodeId}:${h.keyIndex}`] = h.role;
  return map;
}

/**
 * Apply attribute updates via a D3 transition when duration > 0,
 * or synchronously when duration is 0 (keeps tests fast + reliable).
 *
 * @param {d3Selection} selection
 * @param {{ delay, duration }} plan  - timing slot from ChoreographyPlan
 * @param {object}              d3
 * @param {function}            applyFn  - called with (sel) to set attrs
 * @param {function}            [easing] - d3 easing function
 */
function _applyAttrs(selection, plan, d3, applyFn, easing) {
  const duration = plan?.duration ?? 0;
  const delay    = plan?.delay    ?? 0;

  if (duration === 0) {
    applyFn(selection);
  } else {
    let t = selection.transition().delay(delay).duration(duration);
    if (easing) t = t.ease(easing);
    applyFn(t);
  }
}

/**
 * Like _applyAttrs but calls .remove() after the transition finishes.
 * For duration=0, removes synchronously.
 */
function _applyAndRemove(selection, plan, d3, applyFn, easing) {
  const duration = plan?.duration ?? 0;
  const delay    = plan?.delay    ?? 0;

  if (duration === 0) {
    applyFn(selection);
    selection.remove();
  } else {
    let t = selection.transition().delay(delay).duration(duration);
    if (easing) t = t.ease(easing);
    applyFn(t);
    t.remove();
  }
}

const DEFAULT_PLAN = {
  nodeEnter:     { delay: 0, duration: 0 },
  nodeExit:      { delay: 0, duration: 0 },
  nodeMove:      { delay: 0, duration: 0 },
  nodeResize:    { delay: 0, duration: 0 },
  keyEnter:      { delay: 0, duration: 0 },
  keyExit:       { delay: 0, duration: 0 },
  keyMove:       { delay: 0, duration: 0 },
  edgeEnter:     { delay: 0, duration: 0 },
  edgeExit:      { delay: 0, duration: 0 },
  edgeReroute:   { delay: 0, duration: 0 },
  highlightFade: { delay: 0, duration: 0 },
  focusChange:   { delay: 0, duration: 0 },
  cameraPan:     { delay: 0, duration: 0 },
};

module.exports = { NodeRenderer };