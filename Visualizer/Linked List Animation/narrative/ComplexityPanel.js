/**
 * NARRATIVE / COMPLEXITY PANEL
 *
 * Displays the time and space complexity of the current operation.
 * Updated once per operation (not per step).
 *
 * Input:  operationKey string  e.g. 'insertAtHead'
 * Output: renders two badges (Time / Space) and a note
 */

import { COMPLEXITY_MAP } from './constants.js';

export class ComplexityPanel {
  /**
   * @param {HTMLElement} containerEl
   */
  constructor(containerEl) {
    this._el = containerEl;
    this._render(null);
  }

  /**
   * Load complexity info for an operation. Call once when the user
   * selects a new operation, before the first step is rendered.
   *
   * @param {string} operationKey  — key into COMPLEXITY_MAP
   */
  loadOperation(operationKey) {
    this._render(COMPLEXITY_MAP[operationKey] ?? null);
  }

  destroy() {
    this._el.innerHTML = '';
  }

  // ─── Private ──────────────────────────────────────────────────────────────

  _render(info) {
    if (!info) {
      this._el.innerHTML = '<span class="cx-empty">—</span>';
      return;
    }

    const timeClass  = info.time === 'O(1)' ? 'cx-badge-fast' : 'cx-badge-slow';
    const spaceClass = info.space === 'O(1)' ? 'cx-badge-fast' : 'cx-badge-slow';

    this._el.innerHTML = `
      <div class="cx-row">
        <div class="cx-item">
          <span class="cx-label">Time</span>
          <span class="cx-badge ${timeClass}">${info.time}</span>
        </div>
        <div class="cx-item">
          <span class="cx-label">Space</span>
          <span class="cx-badge ${spaceClass}">${info.space}</span>
        </div>
      </div>
      <p class="cx-note">${info.note}</p>
    `;
  }
}