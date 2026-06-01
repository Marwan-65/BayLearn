// ComplexityPanel.js
//
// Shows the theoretical complexity for the loaded operation plus a "current
// case" annotation that updates per step based on step.meta.reason and
// step.action. The goal is to connect the abstract O() to what the student
// is watching happen right now.

const { ACTIONS } = require('../core/constants');

// Per-operation complexity data
const COMPLEXITY = {
  search: {
    time:       'O(t · log_t n)',
    space:      'O(h)  --, recursion stack',
    worstCase:  'O(h) comparisons at every level',
    cases: [
      { reason: 'found',     label: 'Key found',          detail: 'Exact match --, stops here' },
      { reason: 'not-found', label: 'Key not found',      detail: 'Reached a leaf without matching' },
    ],
  },
  insert: {
    time:       'O(t · log_t n)',
    space:      'O(h)  --, recursion stack',
    worstCase:  'O(h) splits cascade to root',
    cases: [
      { reason: 'overflow', label: 'Split triggered',     detail: 'Node full --, median promoted' },
    ],
  },
  delete: {
    time:       'O(t · log_t n)',
    space:      'O(h)  --, recursion stack',
    worstCase:  'O(h) merge cascade to root',
    cases: [
      { reason: 'found',    label: 'Direct delete',        detail: 'Key in leaf --, removed cleanly' },
      { reason: 'rotate',   label: 'Borrow from sibling',  detail: 'Three-way key rotation --, O(1) fix' },
      { reason: 'merge',    label: 'Merge required',       detail: 'Both siblings minimal --, O(t) merge' },
      { reason: 'overflow', label: 'Internal node delete', detail: 'Replaced by predecessor' },
    ],
  },
};

// Map action constants to a reason label when meta.reason is absent
const ACTION_REASON_FALLBACK = {
  [ACTIONS.BORROW_LEFT_ROTATE]:  'rotate',
  [ACTIONS.BORROW_RIGHT_ROTATE]: 'rotate',
  [ACTIONS.MERGE_EXECUTE]:       'merge',
  [ACTIONS.MERGE_PREPARE]:       'merge',
  [ACTIONS.MERGE_PULL_SEPARATOR]:'merge',
  [ACTIONS.MERGE_ABSORB_KEYS]:   'merge',
  [ACTIONS.MERGE_REMOVE_NODE]:   'merge',
  [ACTIONS.MERGE_UPDATE_PARENT]: 'merge',
  [ACTIONS.SPLIT_EXECUTE]:       'overflow',
  [ACTIONS.SPLIT_PREPARE]:       'overflow',
  [ACTIONS.OVERFLOW_DETECTED]:   'overflow',
  [ACTIONS.SEARCH_FOUND]:        'found',
  [ACTIONS.SEARCH_NOT_FOUND]:    'not-found',
  [ACTIONS.DELETE_FROM_LEAF]:    'found',
};

class ComplexityPanel {
  /**
   * @param {HTMLElement} container
   * @param {object}      theme
   */
  constructor(container, theme) {
    this._container = container;
    this._theme     = theme;
    this._op        = null;
    this._render(null);
  }

  // ── Public API ──────────────────────────────────────────────────────────────

  loadOperation(op) {
    this._op = op;
    this._render(null);
  }

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

    const T  = this._theme;
    const cx = this._op ? COMPLEXITY[this._op] : null;

    if (!cx) {
      this._container.innerHTML = `
        <div style="
          padding:10px 14px;
          font-size:11px;
          color:${T.TEXT_DIM};
          font-family:${T.UI_FONT};
          font-style:italic;
        ">Select an operation to see complexity.</div>`;
      return;
    }

    const opLabel   = this._op.charAt(0).toUpperCase() + this._op.slice(1);
    const reason    = step?.meta?.reason ?? ACTION_REASON_FALLBACK[step?.action] ?? null;
    const matchCase = reason ? cx.cases.find(c => c.reason === reason) : null;

    const currentCaseBlock = matchCase
      ? `<div style="
          margin-top:8px;
          padding:7px 10px;
          background:${T.BG_SURFACE};
          border:1px solid ${T.GOLD}44;
          border-radius:6px;
        ">
          <div style="font-size:9px;color:${T.GOLD};font-weight:700;letter-spacing:0.6px;margin-bottom:3px;">
            CURRENT CASE
          </div>
          <div style="font-size:11px;color:${T.TEXT};font-weight:600;">${matchCase.label}</div>
          <div style="font-size:10px;color:${T.TEXT_MUTED};margin-top:2px;">${matchCase.detail}</div>
        </div>`
      : '';

    this._container.innerHTML = `
      <div style="padding:10px 14px;font-family:${T.UI_FONT};">
        <div style="
          font-size:9px;
          font-weight:700;
          letter-spacing:0.8px;
          color:${T.TEXT_DIM};
          margin-bottom:8px;
        ">OPERATION: ${opLabel.toUpperCase()}</div>

        <div style="display:flex;flex-direction:column;gap:4px;">
          ${this._complexityRow('Time', cx.time)}
          ${this._complexityRow('Space', cx.space)}
        </div>

        <div style="
          margin-top:8px;
          font-size:10px;
          color:${T.TEXT_DIM};
        ">Worst case: <span style="color:${T.TEXT_MUTED}">${cx.worstCase}</span></div>

        ${currentCaseBlock}
      </div>`;
  }

  _complexityRow(label, value) {
    const T = this._theme;
    return `
      <div style="display:flex;align-items:baseline;gap:8px;">
        <span style="font-size:10px;color:${T.TEXT_DIM};width:36px;flex-shrink:0;">${label}:</span>
        <code style="
          font-family:${T.CODE_FONT};
          font-size:12px;
          color:${T.GOLD_LIGHT};
          font-weight:600;
        ">${value}</code>
      </div>`;
  }
}

module.exports = { ComplexityPanel, COMPLEXITY };