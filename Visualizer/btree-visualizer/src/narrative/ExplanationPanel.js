// ExplanationPanel.js
//
// Renders the human-readable explanation for each step. Split into two parts:
//   "What" --, what just happened (always shown)
//   "Why"  --, the underlying B-tree principle (shown for key steps only)
//
// The left border colour signals the algorithm phase:
//   gold   → act  (a structural change happened)
//   blue   → descend (moving through the tree)
//   muted  → unwind (propagating back up)
//
// This is a plain DOM module --, no D3, no SVG. It receives a container element
// and manages its innerHTML directly.

const PHASE_COLOURS = {
  act:     '#d4a843', // gold
  descend: '#60a5fa', // blue
  unwind:  '#5a4e38', // muted
};

// These structural B-tree terms get slightly bolder styling in the "what" text
const STRUCTURAL_TERMS = [
  'leaf', 'root', 'parent', 'sibling', 'child', 'internal', 'predecessor',
  'median', 'separator', 'overflow', 'underflow', 'split', 'merge', 'borrow',
  'rotate', 'promote',
];

class ExplanationPanel {
  /**
   * @param {HTMLElement} container  - the DOM element to render into
   * @param {object}      theme      - full theme from createTheme()
   */
  constructor(container, theme) {
    this._container = container;
    this._theme     = theme;
    this._lastPhase = null;
    this._render(null);
  }

  // ── Public API ──────────────────────────────────────────────────────────────

  /**
   * Update the panel for the new step.
   * @param {Step} step
   */
  update(step) {
    this._render(step);
  }

  /** Reset to blank state (called when loadOperation fires). */
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

    if (!step) {
      this._container.innerHTML = this._shell('', '', false, 'descend');
      return;
    }

    const phase       = step.meta?.phase ?? 'descend';
    const isKey       = step.isKeyStep ?? false;
    const explanation = step.explanation ?? '';

    // Split the explanation into what/why. The convention used in the
    // step-generator is that sentences beyond the first are the "why" context.
    // We split on '. ' but keep the first sentence intact.
    const sentences = explanation.split(/\.\s+/);
    const what = sentences[0] + (sentences.length > 1 ? '.' : '');
    const why  = sentences.length > 1 ? sentences.slice(1).join('. ') : '';

    this._container.innerHTML = this._shell(what, why, isKey, phase);
    this._lastPhase = phase;
  }

  _shell(what, why, isKey, phase) {
    const T       = this._theme;
    const border  = PHASE_COLOURS[phase] ?? PHASE_COLOURS.descend;
    const phaseLabel = this._phaseLabel(phase);

    const badge = isKey
      ? `<span style="
          display:inline-block;
          background:${T.GOLD_BG};
          color:${T.GOLD};
          border:1px solid ${T.GOLD};
          border-radius:4px;
          font-size:9px;
          font-weight:700;
          letter-spacing:0.8px;
          padding:2px 7px;
          margin-bottom:8px;
          font-family:${T.UI_FONT};
        ">KEY STEP</span>`
      : '';

    const whyBlock = why
      ? `<p style="
          margin:6px 0 0;
          font-size:12px;
          color:${T.TEXT_MUTED};
          font-family:${T.UI_FONT};
          line-height:1.5;
        ">${this._tokeniseWhy(why)}</p>`
      : '';

    return `
      <div style="
        border-left:3px solid ${border};
        padding:10px 14px;
        transition:border-color 0.25s;
      ">
        <div style="
          display:flex;
          align-items:center;
          gap:8px;
          margin-bottom:${isKey ? '6px' : '4px'};
        ">
          ${badge}
          <span style="
            font-size:9px;
            font-weight:600;
            color:${border};
            font-family:${T.UI_FONT};
            letter-spacing:0.6px;
            opacity:0.8;
          ">${phaseLabel}</span>
        </div>
        <p style="
          margin:0;
          font-size:13px;
          color:${T.TEXT};
          font-family:${T.UI_FONT};
          line-height:1.55;
        ">${what ? this._tokeniseWhat(what) : '<em style="opacity:0.4">Waiting for operation&hellip;</em>'}</p>
        ${whyBlock}
      </div>
    `;
  }

  _phaseLabel(phase) {
    if (phase === 'act')     return 'ACT';
    if (phase === 'unwind')  return 'UNWIND ↑';
    return 'DESCEND ↓';
  }

  // Tokenise the "what" text: highlight node IDs, key values, and structural terms
  _tokeniseWhat(text) {
    return this._tokenise(text, true);
  }

  _tokeniseWhy(text) {
    return this._tokenise(text, false);
  }

  _tokenise(text, highlightTerms) {
    const T = this._theme;
    if (!text) return '';

    // Escape HTML first
    let out = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    // Node IDs: n\d+ or node_\d+ → blue chip
    out = out.replace(
      /\b(n\d+|node_\d+)\b/gi,
      `<code style="background:${T.BLUE_BG};color:${T.BLUE};padding:1px 5px;border-radius:3px;font-size:11px;font-family:${T.CODE_FONT}">$1</code>`
    );

    // Numbers adjacent to comparison operators or standalone → rose
    out = out.replace(
      /\b(\d+)\b/g,
      `<span style="color:#f9a8d4;font-family:${T.CODE_FONT};font-weight:600">$1</span>`
    );

    // Math-style expressions: 2t-1, t-1, 2t etc. → gold
    out = out.replace(
      /\b(2t[-−]1|t[-−]1|2t)\b/g,
      `<span style="color:${T.GOLD};font-weight:600">$1</span>`
    );

    if (highlightTerms) {
      // Structural terms → slightly bold
      for (const term of STRUCTURAL_TERMS) {
        const re = new RegExp(`\\b(${term}s?)\\b`, 'gi');
        out = out.replace(
          re,
          `<strong style="color:${T.TEXT};font-weight:600">$1</strong>`
        );
      }
    }

    return out;
  }
}

module.exports = { ExplanationPanel };