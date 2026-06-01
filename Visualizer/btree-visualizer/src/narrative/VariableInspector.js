// VariableInspector.js
//
// Shows the interesting variables for the current step as labelled pill chips.
// The main trick: variable values that are node IDs (strings starting with
// "node_") get resolved to the node's key array so students see content
// instead of an opaque identifier.
//
// Variable colour roles (spec section 8.5):
//   node, parent         → blue
//   key, medianIndex     → rose/pink
//   leftSibling,
//   rightSibling         → purple
//   predecessor          → teal
//   t                    → muted (rarely changes, low visual priority)
//   depth, keyIndex,
//   childIndex           → amber

const VAR_COLOURS = {
  node:         { label: '#60a5fa', bg: '#0d1a2a' }, // blue
  parent:       { label: '#60a5fa', bg: '#0d1a2a' },
  leftSibling:  { label: '#c084fc', bg: '#1a0d2a' }, // purple
  rightSibling: { label: '#c084fc', bg: '#1a0d2a' },
  key:          { label: '#f9a8d4', bg: '#2a0d1a' }, // rose
  medianIndex:  { label: '#f9a8d4', bg: '#2a0d1a' },
  predecessor:  { label: '#2dd4bf', bg: '#0d2420' }, // teal
  depth:        { label: '#fb923c', bg: '#2a1408' }, // amber
  keyIndex:     { label: '#fb923c', bg: '#2a1408' },
  childIndex:   { label: '#fb923c', bg: '#2a1408' },
  t:            { label: '#5a4e38', bg: '#1c1710' }, // muted
};

// Variables to suppress --, internal or too noisy for the sidebar
const SUPPRESSED = new Set(['t']); // kept in VAR_COLOURS for colour-lookup but hidden by default

class VariableInspector {
  /**
   * @param {HTMLElement} container
   * @param {object}      theme
   */
  constructor(container, theme) {
    this._container = container;
    this._theme     = theme;
    this._render({}, null);
  }

  // ── Public API ──────────────────────────────────────────────────────────────

  /** Render the variables for a step. */
  update(step) {
    this._render(step.variables ?? {}, step.state ?? null);
  }

  reset() {
    this._render({}, null);
  }

  destroy() {
    if (this._container) this._container.innerHTML = '';
    this._container = null;
  }

  // ── Rendering ────────────────────────────────────────────────────────────────

  _render(variables, state) {
    if (!this._container) return;

    const T       = this._theme;
    const entries = Object.entries(variables).filter(([k]) => !SUPPRESSED.has(k));

    if (entries.length === 0) {
      this._container.innerHTML = `
        <p style="
          margin:0;
          padding:8px 14px;
          font-size:11px;
          color:${T.TEXT_DIM};
          font-family:${T.UI_FONT};
          font-style:italic;
        ">No variables this step.</p>`;
      return;
    }

    const chips = entries.map(([name, raw]) => {
      const display = this._resolve(name, raw, state);
      const colours = VAR_COLOURS[name] ?? { label: T.TEXT_MUTED, bg: T.BG_SURFACE3 };

      return `<div style="
        display:inline-flex;
        align-items:center;
        gap:5px;
        background:${colours.bg};
        border:1px solid ${colours.label}44;
        border-radius:5px;
        padding:3px 9px;
        margin:3px;
      ">
        <span style="
          font-size:10px;
          color:${colours.label};
          opacity:0.7;
          font-family:${T.CODE_FONT};
        ">${this._escHtml(name)}</span>
        <span style="
          font-size:11px;
          color:${T.TEXT};
          font-family:${T.CODE_FONT};
          font-weight:600;
        ">${this._escHtml(String(display))}</span>
      </div>`;
    }).join('');

    this._container.innerHTML = `
      <div style="padding:6px 10px;display:flex;flex-wrap:wrap;">
        ${chips}
      </div>`;
  }

  // Resolve node IDs to their key arrays; leave everything else as-is.
  _resolve(name, value, state) {
    if (typeof value !== 'string') return value;

    // A value looks like a node ID if it starts with 'node_' or 'n' followed
    // by digits --, matches the generateId() pattern from shared.js
    const looksLikeNodeId = /^(node_\d+|n\d+)$/.test(value);
    if (!looksLikeNodeId || !state?.nodes) return value;

    const node = state.nodes[value];
    if (!node) return value;

    return `[${node.keys.join(', ')}]`;
  }

  _escHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
}

module.exports = { VariableInspector, VAR_COLOURS };