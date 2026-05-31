/**
 * NARRATIVE LAYER
 *
 * The public face of the entire narrative subsystem.
 * app.js imports only this class --, the four sub-panels are an
 * implementation detail invisible to the outside world.
 *
 * Responsibilities:
 *   - Instantiate and own the four sub-panels
 *   - Route step data to each panel on every frame
 *   - Track prevStep internally so VariableInspector can diff
 *   - Expose loadOperation() for pre-flight setup before a new op plays
 *
 * ─── Usage (in app.js) ────────────────────────────────────────────────────
 *
 *   const narr = new NarrativeLayer({
 *     complexityEl:  document.getElementById('complexity-panel'),
 *     codeEl:        document.getElementById('code-lines'),
 *     explanationEl: document.getElementById('explanation-text'),
 *     varListEl:     document.getElementById('var-list'),
 *   });
 *
 *   narr.loadOperation('insertAtHead');
 *
 *   ctrl.on('narrative', step => narr.update(step));
 */

import { ExplanationPanel }  from './ExplanationPanel.js';
import { PseudocodePanel }   from './PseudocodePanel.js';
import { VariableInspector } from './VariableInspector.js';
import { ComplexityPanel }   from './ComplexityPanel.js';
import { PSEUDOCODES }       from './constants.js';

export class NarrativeLayer {
  /**
   * @param {object} elements
   * @param {HTMLElement} elements.complexityEl   --, container for complexity badges
   * @param {HTMLElement} elements.codeEl         --, container for pseudocode lines
   * @param {HTMLElement} elements.explanationEl  --, container for explanation text
   * @param {HTMLElement} elements.varListEl      --, container for variable chips
   */
  constructor({ complexityEl, codeEl, explanationEl, varListEl }) {
    this._explanation = new ExplanationPanel(explanationEl);
    this._pseudocode  = new PseudocodePanel(codeEl);
    this._variables   = new VariableInspector(varListEl);
    this._complexity  = new ComplexityPanel(complexityEl);

    // Tracked between frames so VariableInspector can diff
    this._prevStep = null;
  }

  /**
   * Pre-flight setup for a new operation.
   * Call this BEFORE wiring the controller events and BEFORE
   * calling update() for the first time on a new operation.
   *
   * Loads the correct pseudocode array and complexity info.
   *
   * @param {string} operationKey  e.g. 'insertAtHead'
   */
  loadOperation(operationKey) {
    const lines = PSEUDOCODES[operationKey] ?? [];
    this._pseudocode.loadLines(lines);
    this._complexity.loadOperation(operationKey);
    this._prevStep = null;   // reset diff baseline for the new operation
  }

  /**
   * Update all panels for the current step.
   * Called by ctrl.on('narrative', step => narr.update(step)).
   *
   * @param {Step} step
   */
  update(step) {
    this._explanation.update(step);
    this._pseudocode.update(step);
    this._variables.update(step, this._prevStep);

    // IMPORTANT: update prevStep AFTER passing it to the inspector,
    // not before. If you swap these two lines, nothing ever shows as changed.
    this._prevStep = step;
  }

  /**
   * Reset to a blank state (e.g. before a new operation loads).
   * Does not destroy sub-panels --, they can be reused after reset.
   */
  reset() {
    this._prevStep = null;
  }

  /**
   * Tear down all sub-panels and clear the DOM.
   * Call when the component is permanently removed.
   */
  destroy() {
    this._explanation.destroy();
    this._pseudocode.destroy();
    this._variables.destroy();
    this._complexity.destroy();
    this._prevStep = null;
  }
}