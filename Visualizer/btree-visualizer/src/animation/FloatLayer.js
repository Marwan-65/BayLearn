// FloatLayer.js
//
// Manages keys that physically travel through SVG space --, the most visually
// distinctive feature of B-tree animations. Splits, merges, and borrows all
// involve keys that leave their home slot and arc through the air.
//
// The float layer renders into a separate <g class="float-layer"> that sits
// ABOVE both the edges and nodes layers so flying keys are never occluded.
//
// Public API:
//   floatLayer.animateArc(opts)   --, fly one key along a bezier arc
//   floatLayer.animateStaggered() --, fly multiple keys with stagger
//   floatLayer.clear()            --, remove all in-flight elements immediately
//   floatLayer.clearAfter(ms)     --, schedule a clear after a delay
//   floatLayer.destroy()          --, remove the layer element itself

class FloatLayer {
  /**
   * @param {d3Selection} parentG  - the zoom container <g> (same parent as edges/nodes)
   * @param {object}      theme    - full theme from createTheme()
   * @param {object}      d3       - d3 namespace
   */
  constructor(parentG, theme, d3) {
    this._g     = parentG.append('g').attr('class', 'float-layer');
    this._theme = theme;
    this._d3    = d3;
    this._uid   = 0;
  }

  // ── Public API ──────────────────────────────────────────────────────────────

  /**
   * Animate a key value along a quadratic-bezier arc from one position to another.
   *
   * @param {object} opts
   * @param {number} opts.keyValue    - the number to display on the flying key
   * @param {object} opts.from        - { x, y } source centre (absolute SVG coords)
   * @param {object} opts.to          - { x, y } destination centre
   * @param {number} opts.delay       - ms delay before animation starts
   * @param {number} opts.duration    - ms for the arc
   * @param {number} [opts.apexOffset=80]  - px above midpoint for the bezier apex
   * @param {string} [opts.fill]      - text/stroke colour (defaults to theme.GOLD_LIGHT)
   * @param {string} [opts.bgFill]    - rect fill colour (defaults to theme.GOLD_BG)
   * @param {boolean} [opts.scaleUp]  - start slightly larger and settle to 1.0
   * @param {boolean} [opts.bounce]   - use easeBackOut for landing
   * @returns {string} arc element ID (for force-removal if needed)
   */
  animateArc(opts) {
    const d3    = this._d3;
    const theme = this._theme;
    const id    = `float-key-${++this._uid}`;

    const {
      keyValue,
      from,
      to,
      delay      = 0,
      duration   = 500,
      apexOffset = 80,
      fill       = theme.GOLD_LIGHT,
      bgFill     = theme.GOLD_BG,
      scaleUp    = false,
      bounce     = false,
    } = opts;

    const W = theme.SLOT_WIDTH;
    const H = theme.SLOT_HEIGHT;

    // Control point for the quadratic bezier --, sits above the midpoint
    const cpX = (from.x + to.x) / 2;
    const cpY = (from.y + to.y) / 2 - apexOffset;

    // Create the floating key group centred at the source position
    const group = this._g.append('g')
      .attr('class', 'float-key')
      .attr('id', id)
      .attr('transform', `translate(${from.x - W / 2}, ${from.y - H / 2})`)
      .attr('opacity', 0);

    group.append('rect')
      .attr('x', 0).attr('y', 0)
      .attr('width', W).attr('height', H)
      .attr('rx', 6)
      .attr('fill', bgFill)
      .attr('stroke', fill)
      .attr('stroke-width', 1.5);

    group.append('text')
      .attr('x', W / 2).attr('y', H / 2 + 1)
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'middle')
      .attr('font-family',  theme.CODE_FONT)
      .attr('font-size',    theme.KEY_VALUE.size)
      .attr('font-weight',  theme.KEY_VALUE.weight)
      .attr('fill', fill)
      .text(keyValue);

    // Fade in before the arc starts
    group.transition().duration(80).attr('opacity', 1);

    if (duration === 0) {
      // Synchronous: place at destination and stay visible until clear() is called.
      // Do NOT self-remove --, the caller (or clear()) handles teardown.
      // This keeps tests able to read DOM state immediately after calling animateArc().
      group
        .attr('opacity', 1)
        .attr('transform', `translate(${to.x - W / 2}, ${to.y - H / 2})`);
      return id;
    }

    // Animate along the quadratic bezier using a custom tween.
    // We compute the bezier point mathematically --, no reliance on SVG path
    // geometry APIs (which jsdom doesn't implement), just simple math.
    const easing = bounce ? d3.easeBackOut : d3.easeCubicInOut;

    group.transition()
      .delay(delay)
      .duration(duration)
      .ease(easing)
      .attrTween('transform', () => t => {
        // Quadratic bezier: B(t) = (1-t)²·from + 2(1-t)t·cp + t²·to
        const mt  = 1 - t;
        const x   = mt * mt * from.x + 2 * mt * t * cpX + t * t * to.x;
        const y   = mt * mt * from.y + 2 * mt * t * cpY + t * t * to.y;
        const s   = scaleUp ? (1.1 - 0.1 * t) : 1;
        return `translate(${x - W / 2}, ${y - H / 2}) scale(${s})`;
      })
      .on('end', () => group.remove());

    return id;
  }

  /**
   * Animate multiple keys with a per-key stagger delay.
   *
   * @param {Array<{keyValue, from, to}>} keys
   * @param {object} opts  - shared options forwarded to animateArc, plus:
   * @param {number} [opts.stagger=80]  - additional ms delay per key
   */
  animateStaggered(keys, opts = {}) {
    const { stagger = 80, ...rest } = opts;
    keys.forEach((k, i) => {
      this.animateArc({ ...k, ...rest, delay: (rest.delay ?? 0) + i * stagger });
    });
  }

  /** Remove all in-flight float elements immediately. */
  clear() {
    this._g.selectAll('.float-key').remove();
  }

  /**
   * Schedule a clear after `delayMs` milliseconds.
   * @returns {number} timer id (pass to clearTimeout to cancel)
   */
  clearAfter(delayMs) {
    return setTimeout(() => this.clear(), delayMs);
  }

  /** Remove the entire float layer from the DOM. */
  destroy() {
    this._g.remove();
  }
}

module.exports = { FloatLayer };
