
import { VAR_ROLES } from './constants.js';

export class VariableInspector {

  constructor(containerEl) {
    this._el = containerEl;
  }


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


  _makeChip(name, nodeId, step, prevStep) {
    const displayValue = this._resolveValue(nodeId, step.state);

    const prevNodeId = prevStep?.variables?.[name];
    const changed    = prevStep !== null && prevNodeId !== nodeId;

    const role = VAR_ROLES[name] ?? 'default';

    const chip = document.createElement('div');
    chip.className = `var-chip var-role-${role}${changed ? ' var-changed' : ''}`;

    chip.innerHTML = `
      <span class="var-name">${this._escapeHtml(name)}</span>
      <span class="var-eq">=</span>
      <span class="var-val">${this._escapeHtml(String(displayValue))}</span>
      ${changed ? '<span class="var-changed-dot" title="changed this step">●</span>' : ''}
    `;

    if (changed) {
      chip.addEventListener('animationend', () => {
        chip.classList.remove('var-changed');
      }, { once: true });
    }

    return chip;
  }


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