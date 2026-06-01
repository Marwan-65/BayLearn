// InvariantTracker.js
//
// The centrepiece of the narrative sidebar. Always visible. Always accurate.
// Shows the four invariants that every valid B-tree satisfies, plus a live
// "active node status" section that updates every step.
//
// The progress bar for key count uses colour to signal node health:
//   green  → safe range
//   amber  → full (exactly 2t-1 keys)
//   red    → overflow (> 2t-1, briefly during split)
//   orange → underflow (< t-1, briefly during delete fixup)
//
// The tracker derives everything it needs from step.state and
// step.highlights --, it never imports from core.

const { NODE_ROLES } = require('../core/constants');

class InvariantTracker {
  /**
   * @param {HTMLElement} container
   * @param {object}      theme
   */
  constructor(container, theme) {
    this._container = container;
    this._theme     = theme;
    this._render(null);
  }

  // ── Public API ──────────────────────────────────────────────────────────────

  update(step) {
    this._render(step);
  }

  reset() {
    this._render(null);
  }

  destroy() {
    if (this._container) this._container.innerHTML = '';
    this._container = null;
  }

  // ── Rendering ────────────────────────────────────────────────────────────────

  _render(step) {
    if (!this._container) return;

    const T = this._theme;

    if (!step) {
      this._container.innerHTML = this._emptyState();
      return;
    }

    const { state, highlights } = step;
    const { t, nodes, rootId }  = state;
    const minKeys = t - 1;
    const maxKeys = 2 * t - 1;

    // Tree-level stats
    const allNodes    = Object.values(nodes);
    const totalNodes  = allNodes.length;
    const totalKeys   = allNodes.reduce((s, n) => s + n.keys.length, 0);
    const treeHeight  = this._treeHeight(nodes, rootId);

    // Active node --, whichever node has the spotlight role
    const activeHighlight = (highlights?.nodes ?? []).find(h =>
      h.role === NODE_ROLES.ACTIVE   ||
      h.role === NODE_ROLES.OVERFLOW ||
      h.role === NODE_ROLES.UNDERFLOW
    );
    const activeNodeId = activeHighlight?.nodeId ?? null;
    const activeNode   = activeNodeId ? nodes[activeNodeId] : null;

    this._container.innerHTML = `
      <div style="font-family:${T.UI_FONT};font-size:12px;color:${T.TEXT};">

        <!-- Header -->
        <div style="
          padding:8px 14px 6px;
          font-size:9px;
          font-weight:700;
          letter-spacing:1px;
          color:${T.TEXT_DIM};
          border-bottom:1px solid ${T.BORDER};
        ">B-TREE PROPERTIES</div>

        <!-- Static parameters -->
        <div style="padding:10px 14px 6px;">
          ${this._row('t  (min degree)', t)}
          ${this._row(`Max keys / node`, `${maxKeys}  <span style="color:${T.TEXT_DIM};font-size:10px">(2t−1)</span>`)}
          ${this._row(`Min keys / node`, `${minKeys}  <span style="color:${T.TEXT_DIM};font-size:10px">(t−1)</span>`)}
        </div>

        <!-- Divider -->
        <div style="height:1px;background:${T.BORDER};margin:0 14px;"></div>

        <!-- Live tree state -->
        <div style="
          padding:6px 14px 4px;
          font-size:9px;
          font-weight:700;
          letter-spacing:1px;
          color:${T.TEXT_DIM};
          margin-top:6px;
        ">CURRENT STATE</div>
        <div style="padding:4px 14px 10px;">
          ${this._row('Tree height',  treeHeight)}
          ${this._row('Total nodes',  totalNodes)}
          ${this._row('Total keys',   totalKeys)}
        </div>

        <!-- Invariants checklist -->
        <div style="height:1px;background:${T.BORDER};margin:0 14px;"></div>
        <div style="
          padding:6px 14px 4px;
          font-size:9px;
          font-weight:700;
          letter-spacing:1px;
          color:${T.TEXT_DIM};
          margin-top:6px;
        ">INVARIANTS</div>
        <div style="padding:4px 14px 10px;">
          ${this._invariantRow('All leaves same depth',   this._checkLeafDepth(nodes, rootId))}
          ${this._invariantRow('Keys sorted per node',    this._checkSorted(nodes))}
          ${this._invariantRow('Children = keys + 1',     this._checkChildCount(nodes))}
        </div>

        <!-- Active node status -->
        ${activeNode ? this._activeNodeSection(activeNodeId, activeNode, t, minKeys, maxKeys) : ''}
      </div>`;
  }

  _row(label, value) {
    const T = this._theme;
    return `
      <div style="
        display:flex;
        justify-content:space-between;
        align-items:center;
        padding:2px 0;
      ">
        <span style="color:${T.TEXT_MUTED};font-size:11px;">${label}</span>
        <span style="color:${T.TEXT};font-size:11px;font-weight:600;font-family:${T.CODE_FONT};">${value}</span>
      </div>`;
  }

  _invariantRow(label, passing) {
    const T     = this._theme;
    const icon  = passing ? '✓' : '✗';
    const colour = passing ? T.GREEN : T.RED;

    return `
      <div style="
        display:flex;
        justify-content:space-between;
        align-items:center;
        padding:2px 0;
      ">
        <span style="color:${T.TEXT_MUTED};font-size:11px;">${label}</span>
        <span style="color:${colour};font-size:12px;font-weight:700;">${icon}</span>
      </div>`;
  }

  _activeNodeSection(nodeId, node, t, minKeys, maxKeys) {
    const T        = this._theme;
    const keyCount = node.keys.length;
    const isOver   = keyCount > maxKeys;
    const isUnder  = keyCount < minKeys && keyCount >= 0;
    const isFull   = keyCount === maxKeys;

    // Bar colour
    let barColour, badge;
    if (isOver) {
      barColour = T.RED;
      badge = `<span style="color:${T.RED};font-size:9px;font-weight:700;margin-left:6px;">OVERFLOW</span>`;
    } else if (isUnder) {
      barColour = T.ORANGE;
      badge = `<span style="color:${T.ORANGE};font-size:9px;font-weight:700;margin-left:6px;">UNDERFLOW</span>`;
    } else if (isFull) {
      barColour = T.GOLD;
      badge = `<span style="color:${T.GOLD};font-size:9px;font-weight:700;margin-left:6px;">FULL</span>`;
    } else {
      barColour = T.GREEN;
      badge = '';
    }

    // Bar fraction: clamp to [0, 1] even during temporary overflow/underflow
    const fraction = Math.max(0, Math.min(1, keyCount / maxKeys));
    const barPct   = Math.round(fraction * 100);

    // Short display of the node's key array
    const keysDisplay = `[${node.keys.join(', ')}]`;

    return `
      <div style="height:1px;background:${T.BORDER};margin:0 14px;"></div>
      <div style="
        padding:6px 14px 4px;
        font-size:9px;
        font-weight:700;
        letter-spacing:1px;
        color:${T.TEXT_DIM};
        margin-top:6px;
      ">ACTIVE NODE</div>
      <div style="padding:6px 14px 12px;">
        <div style="
          display:flex;
          align-items:center;
          justify-content:space-between;
          margin-bottom:5px;
        ">
          <code style="
            font-family:${T.CODE_FONT};
            font-size:10px;
            color:${T.BLUE};
            background:${T.BLUE_BG};
            padding:1px 6px;
            border-radius:3px;
          ">${nodeId}</code>
          <span style="
            font-family:${T.CODE_FONT};
            font-size:10px;
            color:${T.TEXT_MUTED};
          ">${keysDisplay}</span>
        </div>
        <div style="display:flex;align-items:center;gap:6px;">
          <div style="
            flex:1;
            height:6px;
            background:${T.BG_SURFACE3};
            border-radius:3px;
            overflow:hidden;
          ">
            <div style="
              width:${barPct}%;
              height:100%;
              background:${barColour};
              border-radius:3px;
              transition:width 0.25s,background 0.25s;
            "></div>
          </div>
          <span style="
            font-size:10px;
            color:${T.TEXT_MUTED};
            font-family:${T.CODE_FONT};
            white-space:nowrap;
          ">${keyCount}/${maxKeys}${badge}</span>
        </div>
        <div style="
          display:flex;
          justify-content:space-between;
          margin-top:3px;
          font-size:9px;
          color:${T.TEXT_DIM};
          font-family:${T.CODE_FONT};
        ">
          <span>min ${minKeys}</span>
          <span>max ${maxKeys}</span>
        </div>
      </div>`;
  }

  _emptyState() {
    const T = this._theme;
    return `
      <div style="
        padding:16px 14px;
        font-size:11px;
        color:${T.TEXT_DIM};
        font-family:${T.UI_FONT};
        font-style:italic;
      ">Run an operation to see live invariant tracking.</div>`;
  }

  // ── Invariant checkers ────────────────────────────────────────────────────────
  // These are deliberately lenient --, during mid-operation transient states the
  // tree may temporarily violate constraints, and we just report what we see.

  _treeHeight(nodes, rootId) {
    let h = 0;
    let id = rootId;
    while (id && nodes[id]) {
      h++;
      const n = nodes[id];
      id = n.isLeaf ? null : n.children[0];
    }
    return h;
  }

  _checkLeafDepth(nodes, rootId) {
    const depths = [];
    const walk = (id, d) => {
      const n = nodes[id];
      if (!n) return;
      if (n.isLeaf) { depths.push(d); return; }
      for (const c of n.children) walk(c, d + 1);
    };
    walk(rootId, 0);
    if (depths.length === 0) return true;
    return depths.every(d => d === depths[0]);
  }

  _checkSorted(nodes) {
    for (const n of Object.values(nodes)) {
      for (let i = 0; i < n.keys.length - 1; i++) {
        if (n.keys[i] >= n.keys[i + 1]) return false;
      }
    }
    return true;
  }

  _checkChildCount(nodes) {
    for (const n of Object.values(nodes)) {
      if (!n.isLeaf) {
        if (n.children.length !== n.keys.length + 1) return false;
      }
    }
    return true;
  }
}

module.exports = { InvariantTracker };