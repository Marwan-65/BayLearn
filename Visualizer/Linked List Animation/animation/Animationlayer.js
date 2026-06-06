
import { getOrderedIds, NODE_ROLES } from '../schema/index.js';
import { computeHorizontalLayout }   from './LayoutEngine.js';
import { plan as choreograph }        from './TransitionChoreographer.js';
import { DEFAULT_THEME }              from './ThemeModule.js';

export class AnimationLayer {

  constructor(svgEl, d3, theme = DEFAULT_THEME) {
    this._svg   = d3.select(svgEl);
    this._d3    = d3;
    this._theme = theme;
    this._prev  = null;   // previous step, for choreography

    this._width  = svgEl.clientWidth  || 800;
    this._height = svgEl.clientHeight || 400;

    this._setupDefs();
    this._setupLayers();
    this._setupZoom();
  }


  render(step) {
    const positions = computeHorizontalLayout(step.state, this._theme);
    const cp        = choreograph(this._prev, step, this._theme);
    const roleMap   = this._buildRoleMap(step);

    this._renderNodes(step.state, positions, roleMap, cp);
    this._renderArrows(step.state, positions, roleMap, cp);
    this._renderVariableLabels(step.variables, positions, cp);
    this._renderHeadTailBadges(step.state, positions, cp);
    this._panToActive(positions, roleMap);

    this._prev = step;
  }

  setTheme(theme) {
    this._theme = theme;
    this._setupDefs();   // rebuild arrowhead markers with new colors
  }

  resize(width, height) {
    this._width  = width;
    this._height = height;
  }

  destroy() {
    this._svg.selectAll('*').remove();
  }


  _setupDefs() {
    this._svg.select('defs').remove();
    const defs = this._svg.append('defs');

    const T = this._theme;
    Object.entries(T.pointerRoles).forEach(([role, style]) => {
      defs.append('marker')
        .attr('id',          `arrow-${role}`)
        .attr('viewBox',     '0 -5 10 10')
        .attr('refX',        10)
        .attr('refY',        0)
        .attr('markerWidth', T.arrowSize)
        .attr('markerHeight',T.arrowSize)
        .attr('orient',      'auto')
        .append('path')
          .attr('d',    'M0,-5L10,0L0,5')
          .attr('fill', style.stroke);
    });

    const glow = defs.append('filter').attr('id', 'glow');
    glow.append('feGaussianBlur').attr('stdDeviation', '3').attr('result', 'blur');
    glow.append('feMerge').selectAll('feMergeNode')
      .data(['blur', 'SourceGraphic'])
      .join('feMergeNode')
        .attr('in', d => d);
  }

  _setupLayers() {
    this._layerGrid    = this._svg.append('g').attr('class', 'layer-grid');
    this._layerArrows  = this._svg.append('g').attr('class', 'layer-arrows');
    this._layerNodes   = this._svg.append('g').attr('class', 'layer-nodes');
    this._layerLabels  = this._svg.append('g').attr('class', 'layer-labels');

    this._innerG = this._svg.append('g').attr('class', 'zoom-container');
    this._svg.node().appendChild(this._layerGrid.node());

    this._svg.selectAll('g.layer-grid, g.layer-arrows, g.layer-nodes, g.layer-labels').remove();
    this._innerG      = this._svg.append('g').attr('class', 'zoom-container');
    this._layerArrows = this._innerG.append('g').attr('class', 'layer-arrows');
    this._layerNodes  = this._innerG.append('g').attr('class', 'layer-nodes');
    this._layerLabels = this._innerG.append('g').attr('class', 'layer-labels');
  }

  _setupZoom() {
    const d3   = this._d3;
    this._zoom = d3.zoom()
      .scaleExtent([0.3, 2.5])
      .on('zoom', (event) => {
        this._innerG.attr('transform', event.transform);
        this._currentTransform = event.transform;
      });
    this._svg.call(this._zoom);
    this._currentTransform = d3.zoomIdentity;
  }


  _buildRoleMap(step) {
    const map = {};
    (step.highlights?.nodes ?? []).forEach(h => {
      map[h.nodeId] = h.role;
    });
    return map;
  }

  _roleStyle(nodeId, roleMap) {
    const role  = roleMap[nodeId] ?? NODE_ROLES.DEFAULT;
    return this._theme.nodeRoles[role] ?? this._theme.nodeRoles.default;
  }

  _pointerRoleStyle(fromId, toId, step) {
    const ph = (step?.highlights?.pointers ?? [])
      .find(p => p.fromId === fromId && p.toId === toId);
    const role = ph?.role ?? 'default';
    return { role, style: this._theme.pointerRoles[role] ?? this._theme.pointerRoles.default };
  }


  _renderNodes(state, positions, roleMap, cp) {
    const d3    = this._d3;
    const T     = this._theme;
    const nodeW = T.nodeValueW + T.nodeNextW;

    const orderedIds = getOrderedIds(state);
    const nodeData   = orderedIds.map(id => ({
      id,
      node:  state.nodes[id],
      pos:   positions[id],
      style: this._roleStyle(id, roleMap),
    }));

    const groups = this._layerNodes
      .selectAll('g.node')
      .data(nodeData, d => d.id);

    groups.exit()
      .transition().delay(cp.nodeExit.delay).duration(cp.nodeExit.duration)
        .style('opacity', 0)
        .attr('transform', d => {
          const pos = d.pos || { x: 0, y: T.rowY };
          return `translate(${pos.x},${pos.y}) scale(0.6)`;
        })
      .remove();

    const entered = groups.enter()
      .append('g')
        .attr('class', 'node')
        .attr('transform', d => `translate(${d.pos.x},${d.pos.y})`)
        .style('opacity', 0.01);

    entered.append('rect')
      .attr('class', 'value-box')
      .attr('x',      -nodeW / 2)
      .attr('y',      -T.nodeH / 2)
      .attr('width',   T.nodeValueW)
      .attr('height',  T.nodeH)
      .attr('rx',      T.nodeRx)
      .attr('ry',      T.nodeRx)
      .attr('fill',    d => d.style.fill)
      .attr('stroke',  d => d.style.stroke)
      .attr('stroke-width', 1.5);

    entered.append('rect')
      .attr('class', 'next-box')
      .attr('x',     -nodeW / 2 + T.nodeValueW)
      .attr('y',     -T.nodeH / 2)
      .attr('width',  T.nodeNextW)
      .attr('height', T.nodeH)
      .attr('rx',     T.nodeRx)
      .attr('ry',     T.nodeRx)
      .attr('fill',   d => d.style.nextBoxFill)
      .attr('stroke', d => d.style.stroke)
      .attr('stroke-width', 1.5);

    entered.append('line')
      .attr('class', 'divider')
      .attr('x1', -nodeW / 2 + T.nodeValueW)
      .attr('y1', -T.nodeH / 2 + 4)
      .attr('x2', -nodeW / 2 + T.nodeValueW)
      .attr('y2',  T.nodeH / 2 - 4)
      .attr('stroke', d => d.style.stroke)
      .attr('stroke-width', 1)
      .attr('stroke-opacity', 0.4);

    entered.append('text')
      .attr('class', 'value-text')
      .attr('x',            -nodeW / 2 + T.nodeValueW / 2)
      .attr('y',             0)
      .attr('text-anchor',  'middle')
      .attr('dominant-baseline', 'central')
      .attr('font-family',  T.fontFamily)
      .attr('font-size',    T.valueFontSize)
      .attr('font-weight',  '600')
      .attr('fill',         d => d.style.textFill)
      .text(d => d.node.value);

    entered.append('text')
      .attr('class', 'next-symbol')
      .attr('x',            -nodeW / 2 + T.nodeValueW + T.nodeNextW / 2)
      .attr('y',             0)
      .attr('text-anchor',  'middle')
      .attr('dominant-baseline', 'central')
      .attr('font-family',  T.fontFamily)
      .attr('font-size',    14)
      .attr('fill',         d => d.style.stroke)
      .text('→');

    const enteredFade = entered.transition('node-fade')
      .delay(cp.nodeEnter.delay)
      .duration(cp.nodeEnter.duration)
      .style('opacity', 1);

    enteredFade.transition('node-enter-move')
      .delay(cp.nodeMove.delay)
      .duration(cp.nodeMove.duration)
      .attr('transform', d => `translate(${d.pos.x},${d.pos.y})`)
      .style('opacity', 1);

    const merged = entered.merge(groups);

    groups.transition('node-move')
      .delay(cp.nodeMove.delay)
      .duration(cp.nodeMove.duration)
        .attr('transform', d => `translate(${d.pos.x},${d.pos.y})`)
        .style('opacity', 1);

    merged.transition('node-color-value')
      .delay(cp.colorChange.delay)
      .duration(cp.colorChange.duration)
        .select('.value-box')
          .attr('fill',   d => d.style.fill)
          .attr('stroke', d => d.style.stroke)
          .attr('stroke-width', 1.5);

    merged.transition('node-color-next')
      .delay(cp.colorChange.delay)
      .duration(cp.colorChange.duration)
        .select('.next-box')
          .attr('fill',   d => d.style.nextBoxFill)
          .attr('stroke', d => d.style.stroke)
          .attr('stroke-width', 1.5);

    merged.transition('node-color-text')
      .delay(cp.colorChange.delay)
      .duration(cp.colorChange.duration)
        .select('.value-text')
          .attr('fill', d => d.style.textFill);

    merged.transition('node-color-symbol')
      .delay(cp.colorChange.delay)
      .duration(cp.colorChange.duration)
        .select('.next-symbol')
          .attr('fill', d => d.style.stroke);

    merged.select('.divider')
      .attr('stroke', d => d.style.stroke)
      .attr('stroke-width', 1)
      .attr('stroke-opacity', 0.4);
  }


  _renderArrows(state, positions, roleMap, cp) {
    const d3 = this._d3;
    const T  = this._theme;

    const arrowData = [];
    const orderedIds = getOrderedIds(state);

    orderedIds.forEach(fromId => {
      const node   = state.nodes[fromId];
      const toId   = node.next;

      if (toId !== null && positions[toId]) {
        const { role, style } = this._pointerRoleStyle(fromId, toId, this._prev);
        arrowData.push({
          key:    `${fromId}->${toId}`,
          fromId, toId,
          type:   'link',
          role,   style,
          from:   positions[fromId],
          to:     positions[toId],
        });
      } else {
        // Null stub
        arrowData.push({
          key:   `${fromId}->null`,
          fromId, toId: null,
          type:  'null',
          role:  'default',
          style: T.pointerRoles.default,
          from:  positions[fromId],
          to:    null,
        });
      }
    });

    const paths = this._layerArrows
      .selectAll('g.arrow')
      .data(arrowData, d => d.key);

    // EXIT
    paths.exit()
      .transition().delay(cp.arrowExit.delay).duration(cp.arrowExit.duration)
        .style('opacity', 0)
      .remove();

    // ENTER
    const entered = paths.enter()
      .append('g')
        .attr('class', 'arrow')
        .style('opacity', 0);

    entered.append('path').attr('class', 'arrow-path');

    entered.transition()
      .delay(cp.arrowEnter.delay)
      .duration(cp.arrowEnter.duration)
        .style('opacity', 1);

    // MERGE
    const merged = entered.merge(paths);

    merged.transition()
      .delay(cp.arrowReroute.delay)
      .duration(cp.arrowReroute.duration)
        .select('.arrow-path')
          .attr('d',            d => this._arrowPath(d, T))
          .attr('stroke',       d => d.style.stroke)
          .attr('stroke-width', T.arrowStrokeW)
          .attr('stroke-dasharray', d => d.style.dasharray || null)
          .attr('fill',         'none')
          .attr('marker-end',   d => `url(#arrow-${d.role})`);

    // Null label
    this._layerArrows.selectAll('text.null-label').remove();
    arrowData.filter(d => d.type === 'null').forEach(d => {
      const nodeW = T.nodeValueW + T.nodeNextW;
      const sx    = d.from.x + nodeW / 2 + T.nullStubLen + 6;
      this._layerArrows.append('text')
        .attr('class',      'null-label')
        .attr('x',           sx)
        .attr('y',           d.from.y + 5)
        .attr('fill',        T.pointerRoles.default.stroke)
        .attr('font-family', T.fontFamily)
        .attr('font-size',   11)
        .text('null');
    });
  }

  _arrowPath(d, T) {
    const nodeW = T.nodeValueW + T.nodeNextW;
    const sx = d.from.x + nodeW / 2;
    const sy = d.from.y;

    if (d.type === 'null') {
      const ex = sx + T.nullStubLen;
      return `M${sx},${sy} L${ex},${sy}`;
    }

    const ex = d.to.x - nodeW / 2;
    const ey = d.to.y;

    if (ex > sx + 5) {
      const mx = sx + (ex - sx) * 0.5;
      return `M${sx},${sy} C${mx},${sy} ${mx},${ey} ${ex},${ey}`;
    }

    const arc = T.nodeH * 1.6;
    return [
      `M${sx},${sy}`,
      `C${sx + 20},${sy + arc}`,
      `${ex - 20},${ey + arc}`,
      `${ex},${ey}`,
    ].join(' ');
  }


  _renderVariableLabels(variables, positions, cp) {
    const T   = this._d3;
    const th  = this._theme;

    this._layerLabels.selectAll('g.var-label').remove();

    if (!variables) return;

    Object.entries(variables).forEach(([name, nodeId], i) => {
      if (!nodeId || !positions[nodeId]) return;

      const pos   = positions[nodeId];
      const nodeW = th.nodeValueW + th.nodeNextW;
      const x     = pos.x;
      const y     = pos.y + th.nodeH / 2 + 22 + i * 18;

      const g = this._layerLabels.append('g').attr('class', 'var-label');

      // Connector tick
      g.append('line')
        .attr('x1', x).attr('y1', pos.y + th.nodeH / 2)
        .attr('x2', x).attr('y2', y - 2)
        .attr('stroke', '#64748b').attr('stroke-width', 1)
        .attr('stroke-dasharray', '3 2');

      g.append('rect')
        .attr('x',       x - 28).attr('y', y - 8)
        .attr('width',   56).attr('height', 16)
        .attr('rx',      4)
        .attr('fill',    '#1e293b')
        .attr('stroke',  '#475569')
        .attr('stroke-width', 1);

      g.append('text')
        .attr('x',     x).attr('y', y + 1)
        .attr('text-anchor', 'middle')
        .attr('dominant-baseline', 'central')
        .attr('font-family', th.fontFamily)
        .attr('font-size',   9)
        .attr('fill',        '#94a3b8')
        .text(name);
    });
  }


  _renderHeadTailBadges(state, positions, cp) {
    const th    = this._theme;
    const nodeW = th.nodeValueW + th.nodeNextW;

    this._layerLabels.selectAll('g.badge').remove();

    if (!state.head || !positions[state.head]) return;

    // Head badge
    const headPos = positions[state.head];
    const hy      = headPos.y - th.nodeH / 2 - th.labelOffsetY;

    const hg = this._layerLabels.append('g').attr('class', 'badge head-badge');

    hg.append('line')
      .attr('x1', headPos.x).attr('y1', hy + 18)
      .attr('x2', headPos.x).attr('y2', headPos.y - th.nodeH / 2 - 2)
      .attr('stroke', '#6366f1').attr('stroke-width', 1.5)
      .attr('marker-end', 'url(#arrow-default)');

    hg.append('rect')
      .attr('x', headPos.x - 22).attr('y', hy - 10)
      .attr('width', 44).attr('height', 20)
      .attr('rx', 4)
      .attr('fill', '#1e1b4b').attr('stroke', '#6366f1').attr('stroke-width', 1.5);

    hg.append('text')
      .attr('x', headPos.x).attr('y', hy + 1)
      .attr('text-anchor', 'middle').attr('dominant-baseline', 'central')
      .attr('font-family', th.fontFamily).attr('font-size', 10)
      .attr('fill', '#a5b4fc').attr('font-weight', '600')
      .text('head');

    const orderedIds = getOrderedIds(state);
    const tailId     = orderedIds[orderedIds.length - 1];
    if (tailId && tailId !== state.head && positions[tailId]) {
      const tailPos = positions[tailId];
      const ty      = tailPos.y - th.nodeH / 2 - th.labelOffsetY + 24;

      const tg = this._layerLabels.append('g').attr('class', 'badge tail-badge');

      tg.append('rect')
        .attr('x', tailPos.x - 16).attr('y', ty - 8)
        .attr('width', 32).attr('height', 16)
        .attr('rx', 3)
        .attr('fill', '#0f172a').attr('stroke', '#334155').attr('stroke-width', 1);

      tg.append('text')
        .attr('x', tailPos.x).attr('y', ty + 1)
        .attr('text-anchor', 'middle').attr('dominant-baseline', 'central')
        .attr('font-family', th.fontFamily).attr('font-size', 10)
        .attr('fill', '#64748b')
        .text('tail');
    }
  }


  _panToActive(positions, roleMap) {
    const d3 = this._d3;
    const T  = this._theme;

    const activeId = Object.keys(roleMap).find(id => positions[id]);
    if (!activeId) return;

    const pos    = positions[activeId];
    const nodeW  = T.nodeValueW + T.nodeNextW;
    const cx     = this._width / 2;
    const cy     = this._height / 2;
    const tx     = cx - pos.x;
    const ty     = cy - pos.y;

    this._svg.transition().duration(T.t.nodeMove)
      .call(
        this._zoom.transform,
        this._d3.zoomIdentity.translate(tx, ty)
      );
  }
}


AnimationLayer.prototype.resetView = function(state) {
  const T    = this._theme;
  const ids  = getOrderedIds(state);
  if (!ids.length) return;
 
  const nodeW  = T.nodeValueW + T.nodeNextW;
  const step   = nodeW + T.nodeGap;
  const firstX = 80;
  const lastX  = 80 + (ids.length - 1) * step + nodeW + T.nullStubLen + 60;
  const totalW = lastX - firstX + 40;
 
  const svgEl  = this._svg.node();
  const svgW   = svgEl ? svgEl.clientWidth  : (this._width  || 800);
  const svgH   = svgEl ? svgEl.clientHeight : (this._height || 400);
  const scale  = Math.min(1.0, (svgW - 80) / totalW);
  const tx     = (svgW - totalW * scale) / 2 - firstX * scale + 40;
  const ty     = svgH / 2 - T.rowY * scale;
 
  this._svg.transition().duration(500)
    .call(this._zoom.transform, this._d3.zoomIdentity.translate(tx, ty).scale(scale));
};