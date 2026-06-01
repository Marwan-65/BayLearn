// RecursionDepth.js
//
// Renders a breadcrumb trail showing the path from root to the currently
// active node. This makes the two-phase (descend / unwind) nature of the
// algorithms immediately visible.
//
// Example during insert descent:
//   Root [n1] → n3 → n7  (current, depth 2)
//
// When the unwind phase begins, the trail shrinks from right to left.
//
// The component tracks its own history of visited nodes so it can build the
// trail without any external state. It resets when loadOperation() is called.

class RecursionDepth {
  /**
   * @param {HTMLElement} container
   * @param {object}      theme
   */
  constructor(container, theme) {
    this._container = container;
    this._theme     = theme;
    this._trail     = []; // [{ nodeId, keys }]
    this._render();
  }

  // ── Public API ──────────────────────────────────────────────────────────────

  /** Call when starting a new operation --, clears the breadcrumb trail. */
  loadOperation() {
    this._trail = [];
    this._render();
  }

  /** Update the trail based on the current step. */
  update(step) {
    const { state, meta, highlights } = step;
    const phase = meta?.phase ?? 'descend';
    const depth = meta?.depth ?? 0;

    // Find the currently active node
    const activeHighlight = (highlights?.nodes ?? []).find(
      h => h.role === 'active' || h.role === 'overflow' || h.role === 'underflow'
    );
    const activeId = activeHighlight?.nodeId ?? null;

    if (phase === 'descend' && activeId) {
      const node  = state?.nodes?.[activeId];
      const entry = { nodeId: activeId, keys: node?.keys ?? [] };

      // Trim the trail to the current depth and set this node
      this._trail = [...this._trail.slice(0, depth), entry];

    } else if (phase === 'unwind' && typeof depth === 'number') {
      // On unwind, trim to one below current depth (we're leaving this level)
      this._trail = this._trail.slice(0, Math.max(0, depth));
    }
    // 'act' phase: keep the trail as-is

    this._render();
  }

  reset() {
    this._trail = [];
    this._render();
  }

  destroy() {
    if (this._container) this._container.innerHTML = '';
    this._container = null;
  }

  // ── Rendering ────────────────────────────────────────────────────────────────

  _render() {
    if (!this._container) return;

    const T = this._theme;

    if (this._trail.length === 0) {
      this._container.innerHTML = `
        <div style="
          padding:6px 14px;
          font-size:10px;
          color:${T.TEXT_DIM};
          font-family:${T.UI_FONT};
          font-style:italic;
        ">--,</div>`;
      return;
    }

    const crumbs = this._trail.map((entry, i) => {
      const isLast  = i === this._trail.length - 1;
      const isRoot  = i === 0;
      const colour  = isLast ? T.GOLD_LIGHT : T.TEXT_MUTED;
      const keyStr  = `[${entry.keys.join(', ')}]`;
      const label   = isRoot ? `Root` : `d${i}`;

      const chip = `
        <span title="${keyStr}" style="
          display:inline-flex;
          align-items:center;
          gap:3px;
          background:${isLast ? T.GOLD_BG : T.BG_SURFACE3};
          border:1px solid ${isLast ? T.GOLD + '88' : T.BORDER};
          border-radius:4px;
          padding:2px 7px;
          font-size:10px;
          font-family:${T.CODE_FONT};
          color:${colour};
          ${isLast ? `font-weight:700;` : ''}
        ">
          <span style="color:${T.TEXT_DIM};font-size:9px;margin-right:1px;">${label}</span>
          <span>${entry.nodeId}</span>
        </span>`;

      const arrow = i < this._trail.length - 1
        ? `<span style="color:${T.TEXT_DIM};font-size:10px;padding:0 2px;">→</span>`
        : '';

      return chip + arrow;
    }).join('');

    const depthText = `depth ${this._trail.length - 1}`;

    this._container.innerHTML = `
      <div style="
        padding:5px 14px;
        display:flex;
        align-items:center;
        flex-wrap:wrap;
        gap:2px;
      ">
        ${crumbs}
        <span style="
          font-size:9px;
          color:${T.TEXT_DIM};
          margin-left:4px;
          font-family:${T.UI_FONT};
        ">(${depthText})</span>
      </div>`;
  }
}

module.exports = { RecursionDepth };