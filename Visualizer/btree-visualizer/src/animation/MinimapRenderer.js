// MinimapRenderer.js
//
// Renders a 200×150px overview of the entire tree in the bottom-right corner
// of the main SVG canvas. Updates on every frame. Shows:
//   - All node rectangles (no key values, no slot detail --, just shapes)
//   - All edges as thin lines
//   - A semi-transparent gold rectangle showing what the main camera sees
//
// Clicking anywhere on the minimap fires a callback with the clicked layout
// coordinate so CameraController can teleport the main camera there.
//
// The minimap is implemented as a <g class="minimap-root"> appended directly
// to the main SVG (NOT inside the zoom-container) so it stays fixed in the
// corner regardless of pan/zoom.

const MINIMAP_W = 200;
const MINIMAP_H = 150;
const MINIMAP_PAD = 8;    // internal padding so nodes don't clip the border
const CORNER_GAP  = 16;   // gap from bottom-right corner of the SVG

class MinimapRenderer {
  /**
   * @param {SVGElement} svgEl     - the raw <svg> DOM element (the main canvas)
   * @param {object}     theme     - full theme from createTheme()
   * @param {object}     d3        - d3 namespace
   * @param {function}   [onClickNode]  - callback(nodeId, layoutX, layoutY) on minimap click
   */
  constructor(svgEl, theme, d3, onClickNode) {
    this._svgEl      = svgEl;
    this._svg        = d3.select(svgEl);
    this._theme      = theme;
    this._d3         = d3;
    this._onClickNode = onClickNode ?? null;
    this._lastLayout = null;

    this._buildShell();
  }

  // ── Public API ──────────────────────────────────────────────────────────────

  /**
   * Redraw the minimap. Called after every AnimationLayer.render().
   *
   * @param {LayoutMap}      layout         - current tree layout
   * @param {d3ZoomTransform} zoomTransform - current main camera transform
   */
  update(layout, zoomTransform) {
    if (!layout || Object.keys(layout.nodes).length === 0) return;
    this._lastLayout = layout;
    this._drawNodes(layout);
    this._drawEdges(layout);
    this._drawViewport(layout, zoomTransform);
    this._repositionShell();
  }

  /** Remove the minimap from the SVG entirely. */
  destroy() {
    if (this._root) this._root.remove();
  }

  // ── DOM construction ─────────────────────────────────────────────────────────

  _buildShell() {
    const theme = this._theme;
    const d3    = this._d3;

    // Root group, fixed in bottom-right corner (repositioned by _repositionShell)
    this._root = this._svg.append('g')
      .attr('class', 'minimap-root')
      .style('cursor', 'pointer');

    // Background rect
    this._root.append('rect')
      .attr('class', 'minimap-bg')
      .attr('width',  MINIMAP_W)
      .attr('height', MINIMAP_H)
      .attr('rx', 8)
      .attr('fill',         theme.BG_SURFACE)
      .attr('fill-opacity', 0.92)
      .attr('stroke',       theme.BORDER)
      .attr('stroke-width', 1);

    // "MINIMAP" label
    this._root.append('text')
      .attr('class', 'minimap-label')
      .attr('x', MINIMAP_PAD)
      .attr('y', MINIMAP_PAD + 9)
      .attr('font-family', theme.UI_FONT)
      .attr('font-size',   8)
      .attr('font-weight', 700)
      .attr('fill',        theme.TEXT_DIM)
      .attr('letter-spacing', 1)
      .text('MINIMAP');

    // Clip path so nodes/edges don't bleed outside the background rect
    const clipId = `minimap-clip-${Math.random().toString(36).slice(2, 7)}`;
    this._clipId = clipId;

    const defs = this._svg.select('defs');
    const defsEl = defs.empty()
      ? this._svg.insert('defs', ':first-child')
      : defs;

    defsEl.append('clipPath')
      .attr('id', clipId)
      .append('rect')
      .attr('x', 1).attr('y', 1)
      .attr('width',  MINIMAP_W - 2)
      .attr('height', MINIMAP_H - 2)
      .attr('rx', 8);

    // Content group (clipped)
    this._content = this._root.append('g')
      .attr('class', 'minimap-content')
      .attr('clip-path', `url(#${clipId})`);

    this._edgeGroup = this._content.append('g').attr('class', 'mm-edges');
    this._nodeGroup = this._content.append('g').attr('class', 'mm-nodes');

    // Viewport rectangle drawn on top of content
    this._viewport = this._content.append('rect')
      .attr('class', 'minimap-viewport')
      .attr('fill',         this._theme.GOLD)
      .attr('fill-opacity', 0.12)
      .attr('stroke',       this._theme.GOLD)
      .attr('stroke-width', 1)
      .attr('rx', 2);

    // Click handler --, convert minimap coords back to layout coords
    this._root.on('click', (event) => {
      if (!this._lastLayout || !this._onClickNode) return;

      const [mmX, mmY] = d3.pointer(event, this._root.node());
      const scale  = this._lastMmScale   ?? 1;
      const offX   = this._lastMmOffsetX ?? 0;
      const offY   = this._lastMmOffsetY ?? 0;

      const layoutX = (mmX - offX) / scale;
      const layoutY = (mmY - offY) / scale;

      // Find the closest node to the clicked point
      let closest = null;
      let minDist = Infinity;
      for (const [id, pos] of Object.entries(this._lastLayout.nodes)) {
        const dx = pos.x - layoutX;
        const dy = (pos.y + pos.height / 2) - layoutY;
        const dist = dx * dx + dy * dy;
        if (dist < minDist) { minDist = dist; closest = id; }
      }

      if (closest) this._onClickNode(closest, layoutX, layoutY);
    });

    this._repositionShell();
  }

  _repositionShell() {
    const el   = this._svgEl;
    const svgW = el?.clientWidth  || el?.getBoundingClientRect?.().width  || 800;
    const svgH = el?.clientHeight || el?.getBoundingClientRect?.().height || 600;

    this._root.attr('transform',
      `translate(${svgW - MINIMAP_W - CORNER_GAP}, ${svgH - MINIMAP_H - CORNER_GAP})`
    );
  }

  // ── Drawing ──────────────────────────────────────────────────────────────────

  /**
   * Compute the scale + offset that fits the entire layout inside the minimap
   * content area, with MINIMAP_PAD on each side (below the label).
   */
  _computeMinimapTransform(layout) {
    const positions = Object.values(layout.nodes);
    if (positions.length === 0) return { scale: 1, offX: MINIMAP_PAD, offY: MINIMAP_PAD + 14 };

    let minX =  Infinity, maxX = -Infinity;
    let minY =  Infinity, maxY = -Infinity;
    for (const p of positions) {
      if (p.x - p.width / 2 < minX) minX = p.x - p.width / 2;
      if (p.x + p.width / 2 > maxX) maxX = p.x + p.width / 2;
      if (p.y             < minY) minY = p.y;
      if (p.y + p.height  > maxY) maxY = p.y + p.height;
    }

    const contentW = MINIMAP_W - MINIMAP_PAD * 2;
    const contentH = MINIMAP_H - MINIMAP_PAD * 2 - 14; // 14 for label
    const treeW    = maxX - minX || 1;
    const treeH    = maxY - minY || 1;

    const scale = Math.min(contentW / treeW, contentH / treeH);
    const offX  = MINIMAP_PAD + (contentW - treeW * scale) / 2 - minX * scale;
    const offY  = MINIMAP_PAD + 14 + (contentH - treeH * scale) / 2 - minY * scale;

    return { scale, offX, offY };
  }

  _drawNodes(layout) {
    const theme = this._theme;
    const { scale, offX, offY } = this._computeMinimapTransform(layout);

    // Store for viewport and click-to-teleport calculations
    this._lastMmScale   = scale;
    this._lastMmOffsetX = offX;
    this._lastMmOffsetY = offY;

    const data = Object.entries(layout.nodes).map(([id, pos]) => ({ id, pos }));

    const rects = this._nodeGroup.selectAll('rect.mm-node')
      .data(data, d => d.id);

    rects.enter().append('rect').attr('class', 'mm-node')
      .merge(rects)
      .attr('x',      d => d.pos.x * scale + offX - (d.pos.width * scale) / 2)
      .attr('y',      d => d.pos.y * scale + offY)
      .attr('width',  d => Math.max(d.pos.width  * scale, 2))
      .attr('height', d => Math.max(d.pos.height * scale, 2))
      .attr('rx',     2)
      .attr('fill',   theme.BG_SURFACE3)
      .attr('stroke', theme.BORDER2)
      .attr('stroke-width', 0.5);

    rects.exit().remove();
  }

  _drawEdges(layout) {
    const theme = this._theme;
    const { scale, offX, offY } = this._computeMinimapTransform(layout);

    const data = Object.entries(layout.edges).map(([key, edge]) => ({ key, edge }));

    const lines = this._edgeGroup.selectAll('line.mm-edge')
      .data(data, d => d.key);

    lines.enter().append('line').attr('class', 'mm-edge')
      .merge(lines)
      .attr('x1', d => d.edge.fromDot.x * scale + offX)
      .attr('y1', d => d.edge.fromDot.y * scale + offY)
      .attr('x2', d => d.edge.toNode.x  * scale + offX)
      .attr('y2', d => d.edge.toNode.y  * scale + offY)
      .attr('stroke',       theme.BORDER2)
      .attr('stroke-width', 0.5)
      .attr('opacity',      0.7);

    lines.exit().remove();
  }

  _drawViewport(layout, zoomTransform) {
    if (!zoomTransform) {
      this._viewport.attr('width', 0).attr('height', 0);
      return;
    }

    const { scale: mmScale, offX, offY } = this._computeMinimapTransform(layout);

    const el   = this._svgEl;
    const svgW = el?.clientWidth  || el?.getBoundingClientRect?.().width  || 800;
    const svgH = el?.clientHeight || el?.getBoundingClientRect?.().height || 600;

    // The zoom transform is: screenXY = layoutXY * k + [tx, ty]
    // So the viewport in layout coords is:
    //   left   = -tx / k,  right  = (svgW - tx) / k
    //   top    = -ty / k,  bottom = (svgH - ty) / k
    const k  = zoomTransform.k || 1;
    const tx = zoomTransform.x || 0;
    const ty = zoomTransform.y || 0;

    const viewLeft   = -tx / k;
    const viewTop    = -ty / k;
    const viewWidth  = svgW / k;
    const viewHeight = svgH / k;

    // Convert to minimap coordinates
    this._viewport
      .attr('x',      viewLeft   * mmScale + offX)
      .attr('y',      viewTop    * mmScale + offY)
      .attr('width',  Math.max(viewWidth  * mmScale, 4))
      .attr('height', Math.max(viewHeight * mmScale, 4));
  }
}

module.exports = { MinimapRenderer };