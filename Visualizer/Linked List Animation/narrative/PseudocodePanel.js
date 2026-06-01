/**
 * NARRATIVE / PSEUDOCODE PANEL
 *
 * Renders the pseudocode for the current operation as a list of lines.
 * Highlights the active line (step.pseudocodeLine) on every frame.
 * Applies token-level syntax highlighting when lines are loaded.
 *
 * Inputs:
 *   loadLines(lines)  --, string[]  called once per operation
 *   update(step)      --, Step      called every frame
 */

export class PseudocodePanel {
  /**
   * @param {HTMLElement} containerEl  --, the <div id="code-lines"> element
   */
  constructor(containerEl) {
    this._el    = containerEl;
    this._lines = [];
  }

  /**
   * Load a new pseudocode array. Re-renders the entire panel.
   * Call this BEFORE the first update() for a new operation.
   *
   * @param {string[]} lines
   */
  loadLines(lines) {
    this._lines = lines;
    this._el.innerHTML = lines
      .map((line, i) => `
        <div class="code-line" data-line="${i}">
          <span class="line-num">${i}</span>
          <span class="line-code">${this._highlight(line)}</span>
        </div>`)
      .join('');
  }

  /**
   * Highlight the active pseudocode line for the current step.
   * Does nothing if pseudocodeLine is null.
   *
   * @param {Step} step
   */
  update(step) {
    // Remove active from all lines
    this._el.querySelectorAll('.code-line').forEach(el => {
      el.classList.remove('active');
    });

    if (step.pseudocodeLine === null || step.pseudocodeLine === undefined) return;

    const activeLine = this._el.querySelector(
      `.code-line[data-line="${step.pseudocodeLine}"]`
    );
    if (!activeLine) return;

    activeLine.classList.add('active');

    // Scroll into view if the panel overflows vertically
    activeLine.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  destroy() {
    this._el.innerHTML = '';
    this._lines = [];
  }

  // ─── Syntax highlighting ──────────────────────────────────────────────────

  /**
   * Applies token-level syntax highlighting to a single pseudocode line.
   * Returns an HTML string. Order matters --, more specific patterns first.
   *
   * @param   {string} raw   plain text line
   * @returns {string}       HTML string
   */
  _highlight(raw) {
    // Escape HTML entities first to prevent injection
    let h = raw
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    // Use placeholders so later regexes never rewrite markup we already injected.
    // Placeholders are letters-only to avoid clashes with number highlighting.
    const tokens = {};
    let tokenIndex = 0;
    const toAlphaKey = (n) => {
      let x = n;
      let out = '';
      do {
        out = String.fromCharCode(65 + (x % 26)) + out;
        x = Math.floor(x / 26) - 1;
      } while (x >= 0);
      return out;
    };
    const mark = (html) => {
      const key = `__TOK${toAlphaKey(tokenIndex++)}__`;
      tokens[key] = html;
      return key;
    };

    // 1. Keywords (case-sensitive, word boundaries)
    const keywords = ['WHILE', 'IF', 'THEN', 'ELSE', 'DO', 'END', 'RETURN', 'NULL', 'ERROR'];
    keywords.forEach(kw => {
      h = h.replace(new RegExp(`\\b${kw}\\b`, 'g'), (m) => mark(`<span class="kw">${m}</span>`));
    });

    // 2. Assignment arrow ←
    h = h.replace(/←/g, () => mark('<span class="op">←</span>'));

    // 3. Comparison / arithmetic operators
    h = h.replace(/&lt;/g, () => mark('<span class="op">&lt;</span>'));
    h = h.replace(/&gt;/g, () => mark('<span class="op">&gt;</span>'));
    h = h.replace(/≠/g, () => mark('<span class="op">≠</span>'));
    h = h.replace(/=/g, () => mark('<span class="op">=</span>'));
    h = h.replace(/≥/g, () => mark('<span class="op">≥</span>'));
    h = h.replace(/≤/g, () => mark('<span class="op">≤</span>'));
    h = h.replace(/([+\-−×÷])/g, (m) => mark(`<span class="op">${m}</span>`));

    // 4. Parenthesised parameters like (value), (index)
    h = h.replace(/\(([^)]*)\)/g, (_m, p1) => mark(`(<span class="param">${p1}</span>)`));

    // 5. Property access: word.word
    h = h.replace(
      /\b([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\b/g,
      (_m, p1, p2) => mark(`<span class="prop">${p1}</span><span class="dot">.</span><span class="prop2">${p2}</span>`)
    );

    // 6. Standalone numbers
    h = h.replace(/\b(\d+)\b/g, (_m, p1) => mark(`<span class="num">${p1}</span>`));

    // 7. Comments (anything after a #)
    h = h.replace(/(#.*)$/, (_m, p1) => mark(`<span class="comment">${p1}</span>`));

    // Restore highlighted tokens.
    h = h.replace(/__TOK[A-Z]+__/g, (m) => tokens[m] ?? m);

    return h;
  }
}