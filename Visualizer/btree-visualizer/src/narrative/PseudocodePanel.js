// PseudocodePanel.js
//
// Shows the pseudocode for the current operation with the active line
// highlighted. A small phase badge sits above the code block so students
// can see at a glance where in the algorithm they are.
//
// Each operation (search, insert, delete) has its own pseudocode array
// imported from the core modules. loadOperation() swaps which one is shown.
// update() just highlights the right line.

// Pseudocode is stored here rather than importing from core because the
// narrative layer shouldn't have to dig into algorithm internals.
const PSEUDOCODES = {
  search: [
    'function search(node, key):',
    '  for i = 0 to node.keys.length - 1:',
    '    if key == node.keys[i]: return (node, i)',
    '    if key < node.keys[i]:',
    '      if node.isLeaf: return NOT_FOUND',
    '      return search(node.children[i], key)',
    '  if node.isLeaf: return NOT_FOUND',
    '  return search(node.children[node.keys.length], key)',
  ],
  insert: [
    'function insert(key):',
    '  if root is full (2t-1 keys):',
    '    newRoot = createNode()',
    '    newRoot.children = [root]',
    '    splitChild(newRoot, 0, root)',
    '    root = newRoot',
    '  insertNonFull(root, key)',
    '',
    'function insertNonFull(node, key):',
    '  i = node.keys.length - 1',
    '  if node.isLeaf:',
    '    shift keys right to insert in sorted position',
    '    node.keys.insert(key at correct position)',
    '  else:',
    '    find i such that key > node.keys[i]',
    '    if node.children[i+1] is full:',
    '      splitChild(node, i+1, node.children[i+1])',
    '      if key > node.keys[i+1]: i++',
    '    insertNonFull(node.children[i+1], key)',
    '',
    'function splitChild(parent, i, child):',
    '  newNode = createNode()',
    '  medianKey = child.keys[t-1]',
    '  newNode.keys = child.keys[t:]',
    '  child.keys = child.keys[:t-1]',
    '  if not child.isLeaf:',
    '    newNode.children = child.children[t:]',
    '    child.children = child.children[:t]',
    '  parent.keys.insert(medianKey at position i)',
    '  parent.children.insert(newNode at position i+1)',
  ],
  delete: [
    'function delete(key):',
    '  _delete(root, key)',
    '  if root.keys.length == 0 and root has children:',
    '    root = root.children[0]',
    '',
    'function _delete(node, key):',
    '  i = findPosition(node, key)',
    '  if key found at node.keys[i]:',
    '    if node.isLeaf: remove node.keys[i]',
    '    else:',
    '      pred = getPredecessor(node.children[i])',
    '      node.keys[i] = pred',
    '      _delete(node.children[i], pred)',
    '  else:',
    '    _delete(node.children[i], key)',
    '  fixUnderflow(node)',
  ],
};

const PHASE_LABELS = {
  descend: 'DESCEND ↓',
  act: 'ACT',
  unwind: 'UNWIND ↑',
};

const PHASE_COLOURS = {
  descend: '#60a5fa',
  act: '#d4a843',
  unwind: '#5a4e38',
};

class PseudocodePanel {
  /**
   * @param {HTMLElement} container
   * @param {object}      theme
   */
  constructor(container, theme) {
    this._container = container;
    this._theme = theme;
    this._op = null;
    this._render(null, null);
  }

  // ── Public API ──────────────────────────────────────────────────────────────

  /** Switch to the pseudocode for a new operation. */
  loadOperation(op) {
    this._op = op;
    this._render(null, null);
  }

  /** Highlight the line for this step. */
  update(step) {
    this._render(step.pseudocodeLine, step.meta?.phase ?? 'descend');
  }

  reset() {
    this._render(null, null);
  }

  destroy() {
    if (this._container) this._container.innerHTML = '';
    this._container = null;
  }

  // ── Rendering ────────────────────────────────────────────────────────────────

  _render(activeLine, phase) {
    if (!this._container) return;

    const T = this._theme;
    const code = this._op ? (PSEUDOCODES[this._op] ?? []) : [];

    if (code.length === 0) {
      this._container.innerHTML = `
        <div style="padding:12px 16px;opacity:0.4;font-size:12px;font-family:var(--ui-font);color:${T.TEXT_MUTED}">
          Select an operation to see pseudocode.
        </div>`;
      return;
    }

    const phaseColour = phase ? (PHASE_COLOURS[phase] ?? PHASE_COLOURS.descend) : T.BORDER2;
    const phaseText = phase ? (PHASE_LABELS[phase] ?? '') : '';

    const phaseBar = phase ? `
      <div style="
        padding:4px 14px 8px;
        display:flex;
        align-items:center;
        gap:6px;
      ">
        <span style="
          font-size:9px;
          font-weight:700;
          letter-spacing:0.8px;
          color:${phaseColour};
          font-family:var(--ui-font);
        ">${phaseText}</span>
      </div>` : '';

    const lines = code.map((line, i) => {
      const isActive = i === activeLine;
      const indent = line.match(/^(\s*)/)[1].length;
      const trimmed = line.trimStart();
      const isBlank = trimmed === '';

      const bg = isActive ? 'rgba(6, 182, 212, 0.22)' : 'transparent';
      const colour = isActive ? T.GOLD_LIGHT : T.TEXT_MUTED;
      const border = isActive ? `border-left:3px solid ${T.GOLD};` : 'border-left:3px solid transparent;';
      const lineNumColor = isActive ? T.GOLD_LIGHT : T.TEXT_MUTED;
      const lineNumOpacity = isActive ? 0.9 : 0.4;

      return `<div style="
        ${border}
        background:${bg};
        padding:1px 14px 1px ${isActive ? '11px' : '14px'};
        min-height:${isBlank ? '10px' : '20px'};
        display:flex;
        align-items:center;
        transition:background 0.15s;
      ">
        <span style="
          display:inline-block;
          color:${lineNumColor};
          font-family:var(--code-font);
          font-size:10px;
          width:24px;
          margin-right:12px;
          text-align:right;
          flex-shrink:0;
          user-select:none;
          opacity:${lineNumOpacity};
        ">${isBlank ? '' : i}</span>
        <span style="
          font-family:var(--code-font);
          font-size:11px;
          color:${colour};
          white-space:pre;
          padding-left:${indent * 4}px;
        ">${this._highlight(trimmed)}</span>
      </div>`;
    }).join('');

    this._container.innerHTML = `
      <div style="
        background:${T.BG_SURFACE};
        border:1px solid ${T.BORDER};
        border-radius:8px;
        overflow:hidden;
      ">
        ${phaseBar}
        <div style="padding:4px 0 8px;">
          ${lines}
        </div>
      </div>`;
  }

  // Very minimal keyword highlighting --, just enough to be readable
  _highlight(text) {
    const T = this._theme;
    if (!text) return '';

    return text
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      // keywords
      .replace(
        /\b(function|if|else|return|for|to|not|and|or)\b/g,
        `<span style="color:${T.PURPLE}">$1</span>`
      )
      // numbers
      .replace(
        /\b(\d+)\b/g,
        `<span style="color:#f9a8d4">$1</span>`
      )
      // NOT_FOUND / TRUE / FALSE style constants
      .replace(
        /\b(NOT_FOUND|true|false|null)\b/g,
        `<span style="color:${T.ORANGE}">$1</span>`
      );
  }
}

module.exports = { PseudocodePanel, PSEUDOCODES };