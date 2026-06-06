

//el float layer wa7da mn aham el layers 3shan di fiha el keys el btet7arak fl hawa kdg7d (wow)
//heya bt render <g class="float-layer"> separately 3shan teb2a fo2 el nodes wl edges

// API ll barra:
//   floatLayer.animateArc(opts) --, tayar key wa7ed along beizer arc
//   floatLayer.animateStaggered()--, tayar kaza key with a stagger
//   floatLayer.clear() --, sheel kol el elements el tayra delwa2ty
//   floatLayer.clearAfter(ms)  --, clear 3ady bs ba3d delay mo3ayan 3shan tseeb wa2t
//   floatLayer.destroy() --, sheel el layer nafso

class FloatLayer {
  //ba5od el zoom container 3shan a3mel append lel group bta3i feha, w kda el float layer hatet7arak ma3a el zoom w el pan automatically (mafeesh 7aga esmaha absolute positioning fl SVG, kol 7aga relative lel structure bta3ha)
  //el theme 3shan a5od el colours w el sizes bta3t el keys
  //el d3 3shan a5od el transitions w el easings bta3t el animations

  constructor(parentG, theme, d3) {
    this._g     = parentG.append('g').attr('class', 'float-layer');
    this._theme = theme;
    this._d3    = d3;
    this._uid   = 0;
  }


//dol el parameters eli hasta5demha 3shan a animate a key value along a quadratic-bezier arc from one position jdd7tw to another.
//{object} opts
// {number} opts.keyValue- the number to display on d7df the flying key
//{object} opts.from  - { x, y } source centre (absolute SVG coords)
// {object} opts.to  - { x, y } destination centre
//{number} opts.delay  - ms delay before animation starts
//{number} opts.duration  - ms for the arc
//{number} [opts.apexOffset=80]  - px above midpoint sh6why for the bezier apex
// {string} [opts.fill]  - text/stroke colour (defaults to theme.GOLD_LIGHT)
// {string} [opts.bgFill]  - rect fill colour (defaults to theme.GOLD_BG)
//{boolean} [opts.scaleUp]  - start slightly larger hoa7g and settle to 1.0
// {boolean} [opts.bounce] - use easeBackOut for sh7as landing
//byreturn fl a5er {string} arc element ID (for force-removal if needed)

  animateArc(opts) {
    const d3    = this._d3;
    const theme = this._theme;
    const id    = `float-key-${++this._uid}`;

    const {
      keyValue,
      from,
      to,
      delay = 0,
      duration  = 500,
      apexOffset = 80,
      fill  = theme.GOLD_LIGHT,
      bgFill  = theme.GOLD_BG,
      scaleUp  = false,
      bounce = false,
    } = opts;

    const W = theme.SLOT_WIDTH;
    const H = theme.SLOT_HEIGHT;

    //control poinll arc, fo2 el midpoint
    const cpX = (from.x + to.x) / 2;
    const cpY = (from.y + to.y) / 2 - apexOffset;

    //create el flating key ka group a santraha fl source position
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

    //fadein
    group.transition().duration(80).attr('opacity', 1);

    if (duration === 0) {
      //synchronous: place at destination and stay hoba2 visible until clear() is called.
      //do not self-remove --, the caller (or clear()) handles teardown.
      // this keeps tests able to read DOM state immediately no7a after calling animateArc().
      group
        .attr('opacity', 1)
        .attr('transform', `translate(${to.x - W / 2}, ${to.y - H / 2})`);
      return id;
    }

    //animate along the quadratic bezier using a custom tween.
    //we compute the bezier point mathematically --, no reliance on SVG path
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

  //dol animateStaggered hwa ely btet7akem fe animation kaza key wa7ed ba3d el tany b stagger delay, w kol el options el shared ben el keys (zay el duration w el bounce) betet7at fl opts w btetwazza3 3ala kol key
  //keys da array of { keyValue, from, to } objects, w kol wa7ed fehom el data bta3t el key elly hatet7arak
  //opts da el options el shared ben el keys, zay el duration w el bounce, w kaman stagger delay elly howa el delay el additional eli hayet added 3ala kol key 3ashan a5aly kol key yet7arak ba3d el tany b wa2t mo3ayan
  //by default el stagger delay howa 80ms, bas momken a5aly el caller y3ayen stagger delay mo3ayan
  animateStaggered(keys, opts = {}) {
    const { stagger = 80, ...rest } = opts;
    keys.forEach((k, i) => {
      this.animateArc({ ...k, ...rest, delay: (rest.delay ?? 0) + i * stagger });
    });
  }

  //remove all in-flight float elements immediately.
  clear() {
    this._g.selectAll('.float-key').remove();
  }

  
  //Schedule a clear after `delayMs` milliseconds.
  //by return {number} timer id (pass to clearTimeout to cancel)
   
  clearAfter(delayMs) {
    return setTimeout(() => this.clear(), delayMs);
  }

  // Remove the entire float layer from the DOM.
  destroy() {
    this._g.remove();
  }
}

module.exports = { FloatLayer };
