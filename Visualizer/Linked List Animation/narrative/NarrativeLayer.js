
import { ExplanationPanel }  from './ExplanationPanel.js';
import { PseudocodePanel }   from './PseudocodePanel.js';
import { VariableInspector } from './VariableInspector.js';
import { ComplexityPanel }   from './ComplexityPanel.js';
import { PSEUDOCODES }       from './constants.js';

export class NarrativeLayer {

  constructor({ complexityEl, codeEl, explanationEl, varListEl }) {
    this._explanation = new ExplanationPanel(explanationEl);
    this._pseudocode  = new PseudocodePanel(codeEl);
    this._variables   = new VariableInspector(varListEl);
    this._complexity  = new ComplexityPanel(complexityEl);

    this._prevStep = null;
  }


  loadOperation(operationKey) {
    const lines = PSEUDOCODES[operationKey] ?? [];
    this._pseudocode.loadLines(lines);
    this._complexity.loadOperation(operationKey);
    this._prevStep = null;   // reset diff baseline for the new operation
  }


  update(step) {
    this._explanation.update(step);
    this._pseudocode.update(step);
    this._variables.update(step, this._prevStep);


    this._prevStep = step;
  }

  reset() {
    this._prevStep = null;
  }


  destroy() {
    this._explanation.destroy();
    this._pseudocode.destroy();
    this._variables.destroy();
    this._complexity.destroy();
    this._prevStep = null;
  }
}