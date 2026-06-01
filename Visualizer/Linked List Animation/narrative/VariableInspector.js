/**
 * NARRATIVE / VARIABLE INSPECTOR
 *
 * Renders step.variables as coloured chips.
 *
 * Key features:
 *   1. Resolves node IDs to actual values: shows "current = 20" not "current = n2"
 *   2. Diffs against prevStep.variables: flashes a "changed" animation on updated vars
 *   3. Colour-codes chips by variable name role (amber=current, purple=prev, etc.)
 *
 * Inputs:
 *   update(step, prevStep)  --, both Step objects; prevStep may be null
 */

import { VAR_ROLES } from './constants.js';

export class VariableInspector {
  /**
   * @param {HTMLElement} containerEl  --, the <div id="var-list"> element
   */
  constructor(containerEl) {
    this._el = containerEl;
  }

  /**
   * Re-render the variable chips for the current step.
   *
   * @param {Step}      step
   * @param {Step|null} prevStep  --, previous step, used to detect changes
   */
  update(step, prevStep) {
    const vars = step.variables ?? {};
    this._el.innerHTML = '';

    if (Object.keys(vars).length === 0) {
      this._el.innerHTML = '<span class="var-empty">no active variables</span>';
      return;
    }

    Object.entries(vars).forEach(([name, nodeId]) => {
      const chip = this._makeChip(name, nodeId, step, prevStep);
      this._el.appendChild(chip);
    });
  }

  destroy() {
    this._el.innerHTML = '';
  }

  // ─── Private ──────────────────────────────────────────────────────────────

  /**
   * Build a single variable chip element.
   *
   * @param {string}    name      variable name e.g. "current"
   * @param {string|null} nodeId  node ID e.g. "n2", or null
   * @param {Step}      step
   * @param {Step|null} prevStep
   * @returns {HTMLElement}
   */
  _makeChip(name, nodeId, step, prevStep) {
    // Resolve node ID → display value
    const displayValue = this._resolveValue(nodeId, step.state);

    // Detect whether this variable changed since the last step
    const prevNodeId = prevStep?.variables?.[name];
    const changed    = prevStep !== null && prevNodeId !== nodeId;

    // Determine colour role
    const role = VAR_ROLES[name] ?? 'default';

    const chip = document.createElement('div');
    chip.className = `var-chip var-role-${role}${changed ? ' var-changed' : ''}`;

    chip.innerHTML = `
      <span class="var-name">${this._escapeHtml(name)}</span>
      <span class="var-eq">=</span>
      <span class="var-val">${this._escapeHtml(String(displayValue))}</span>
      ${changed ? '<span class="var-changed-dot" title="changed this step">●</span>' : ''}
    `;

    // Remove the "changed" flash class after the animation completes
    // so it re-triggers properly on the next change
    if (changed) {
      chip.addEventListener('animationend', () => {
        chip.classList.remove('var-changed');
      }, { once: true });
    }

    return chip;
  }

  /**
   * Resolve a nodeId to a human-readable display string.
   * Returns the node's value if resolvable, "null" if nodeId is null,
   * or the nodeId itself as a fallback.
   *
   * @param {string|null} nodeId
   * @param {ListState}   state
   * @returns {string}
   */
  _resolveValue(nodeId, state) {
    if (nodeId === null || nodeId === undefined) return 'null';
    const node = state?.nodes?.[nodeId];
    if (!node) return nodeId;          // fallback: show raw ID
    return String(node.value);
  }

  _escapeHtml(str) {
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }
}