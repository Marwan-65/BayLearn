// NarrativeLayer.js
//
// The public face of the entire narrative system. Everything outside this
// directory imports NarrativeLayer and nothing else.
//
// It owns five sub-panels and mounts each one into a child div it creates
// inside the container element. The container is expected to be the sidebar
// <div id="narrative"> from index.html.
//
// Usage (from app.js in Stage 8):
//   const narr = new NarrativeLayer(document.getElementById('narrative'), theme);
//   narr.loadOperation('insert');
//   playbackCtrl.on('narrative', (step, prev) => narr.update(step, prev));

const { ExplanationPanel }  = require('./ExplanationPanel');
const { PseudocodePanel }   = require('./PseudocodePanel');
const { VariableInspector } = require('./VariableInspector');
const { InvariantTracker }  = require('./InvariantTracker');
const { ComplexityPanel }   = require('./ComplexityPanel');
const { RecursionDepth }    = require('./RecursionDepth');
const { createTheme }       = require('../animation/ThemeModule');

// Section IDs --, these become the ids on the child divs so CSS can target them
const SECTION_IDS = {
  invariant:   'narr-invariant',
  recursion:   'narr-recursion',
  pseudocode:  'narr-pseudocode',
  explanation: 'narr-explanation',
  variables:   'narr-variables',
  complexity:  'narr-complexity',
};

class NarrativeLayer {
  /**
   * @param {HTMLElement} container     - the sidebar DOM element
   * @param {object}      [themeOverrides] - optional partial theme
   */
  constructor(container, themeOverrides = {}) {
    this._container = container;
    this._theme     = createTheme(themeOverrides);
    this._op        = null;

    this._buildLayout();
    this._buildPanels();
  }

  // ── Public API ──────────────────────────────────────────────────────────────

  /**
   * Prepare the sidebar for a new operation. Swaps pseudocode, resets panels.
   * @param {'search'|'insert'|'delete'} op
   */
  loadOperation(op) {
    this._op = op;
    this._pseudocode.loadOperation(op);
    this._complexity.loadOperation(op);
    this._recursion.loadOperation();
    this._explanation.reset();
    this._variables.reset();
    this._invariant.reset();
  }

  /**
   * Update all panels for the new step.
   * @param {Step}      step
   * @param {Step|null} prevStep
   */
  update(step, prevStep) {
    this._invariant.update(step);
    this._recursion.update(step);
    this._explanation.update(step);
    this._pseudocode.update(step);
    this._variables.update(step);
    this._complexity.update(step);
  }

  /** Tear down --, empties the container. */
  destroy() {
    this._invariant.destroy();
    this._recursion.destroy();
    this._pseudocode.destroy();
    this._explanation.destroy();
    this._variables.destroy();
    this._complexity.destroy();
    if (this._container) this._container.innerHTML = '';
    this._container = null;
  }

  // Exposed for testing
  get panels() {
    return {
      invariant:   this._invariant,
      recursion:   this._recursion,
      pseudocode:  this._pseudocode,
      explanation: this._explanation,
      variables:   this._variables,
      complexity:  this._complexity,
    };
  }

  // ── DOM construction ─────────────────────────────────────────────────────────

  _buildLayout() {
    const T = this._theme;

    this._container.style.cssText = `
      display:flex;
      flex-direction:column;
      gap:0;
      background:${T.BG_SURFACE2};
      height:100%;
      overflow-y:auto;
      font-family:${T.UI_FONT};
      color:${T.TEXT};
    `;

    // Create a child div for each section in sidebar order
    const sections = [
      { id: SECTION_IDS.invariant,   label: 'Properties' },
      { id: SECTION_IDS.recursion,   label: 'Call Stack' },
      { id: SECTION_IDS.pseudocode,  label: 'Pseudocode' },
      { id: SECTION_IDS.explanation, label: 'Explanation' },
      { id: SECTION_IDS.variables,   label: 'Variables' },
      { id: SECTION_IDS.complexity,  label: 'Complexity' },
    ];

    this._container.innerHTML = sections.map(s => `
      <div class="narr-section" style="
        border-bottom:1px solid ${T.BORDER};
      ">
        <div id="${s.id}-header" style="
          padding:8px 14px 4px;
          font-size:9px;
          font-weight:700;
          letter-spacing:1px;
          color:${T.TEXT_DIM};
          cursor:default;
          user-select:none;
        ">${s.label.toUpperCase()}</div>
        <div id="${s.id}"></div>
      </div>`).join('');
  }

  _buildPanels() {
    const T   = this._theme;
    const get = id => this._container.querySelector(`#${id}`);

    this._invariant  = new InvariantTracker(get(SECTION_IDS.invariant),   T);
    this._recursion  = new RecursionDepth(  get(SECTION_IDS.recursion),   T);
    this._pseudocode = new PseudocodePanel( get(SECTION_IDS.pseudocode),  T);
    this._explanation= new ExplanationPanel(get(SECTION_IDS.explanation), T);
    this._variables  = new VariableInspector(get(SECTION_IDS.variables),  T);
    this._complexity = new ComplexityPanel( get(SECTION_IDS.complexity),  T);
  }
}

module.exports = { NarrativeLayer };