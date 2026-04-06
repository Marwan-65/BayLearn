/**
 * NARRATIVE / EXPLANATION PANEL
 *
 * Renders step.explanation as richly formatted HTML.
 * Detects patterns in the explanation string and wraps them
 * in styled spans without touching any other layer.
 *
 * Input:  step.explanation  (plain string from the operation layer)
 * Output: innerHTML of the container element
 */

export class ExplanationPanel {
  /**
   * @param {HTMLElement} containerEl  — the element to render into
   */
  constructor(containerEl) {
    this._el = containerEl;
  }

  /**
   * Re-render the explanation for the given step.
   * @param {Step} step
   */
  update(step) {
    this._el.innerHTML = this._format(step.explanation ?? '');
  }

  destroy() {
    this._el.innerHTML = '';
  }

  // ─── Private ──────────────────────────────────────────────────────────────

  /**
   * Applies formatting rules to a raw explanation string and
   * returns an HTML string. Rules are applied in a specific order
   * to avoid double-substitution.
   *
   * @param   {string} text
   * @returns {string}  HTML string safe to assign to innerHTML
   */
  _format(text) {
    // 1. Escape any existing HTML characters to prevent XSS
    let html = this._escape(text);

    // 2. Emoji-prefixed sentence types — apply to whole logical sentences.
    //    Split on sentence-ending punctuation to wrap each sentence independently.
    html = html.replace(
      /(⚠️[^.!?\n]+[.!?]?)/g,
      '<span class="exp-warning">$1</span>'
    );
    html = html.replace(
      /(❌[^.!?\n]+[.!?]?)/g,
      '<span class="exp-error">$1</span>'
    );
    html = html.replace(
      /(✅[^.!?\n]+[.!?]?)/g,
      '<span class="exp-success">$1</span>'
    );

    // 3. Code-style patterns: word.word (property access like current.next)
    html = html.replace(
      /\b([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\b/g,
      '<code class="exp-prop">$1<span class="exp-dot">.</span>$2</code>'
    );

    // 4. Pointer arrow symbol ← used in pseudocode references
    html = html.replace(/←/g, '<span class="exp-arrow">←</span>');

    // 5. Quoted values like "value: 42" or standalone integers in context
    //    Match numbers that are wrapped in word boundaries
    html = html.replace(
      /\bvalue\s*:\s*(\d+)/g,
      'value: <span class="exp-value">$1</span>'
    );
    html = html.replace(
      /O\(([^)]+)\)/g,
      'O(<span class="exp-complexity">$1</span>)'
    );

    // 6. Quoted variable names in backtick style if author uses them
    html = html.replace(
      /`([^`]+)`/g,
      '<code class="exp-inline-code">$1</code>'
    );

    // 7. Convert newline characters to <br> for multi-line explanations
    html = html.replace(/\n/g, '<br>');

    return html;
  }

  _escape(str) {
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
}