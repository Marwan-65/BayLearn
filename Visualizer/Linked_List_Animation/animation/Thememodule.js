/**
 * ANIMATION / THEME MODULE
 *
 * Single source of truth for every colour, size, and timing constant
 * used by the renderers. No hardcoded values anywhere else.
 *
 * Swap the entire theme at runtime via AnimationLayer.setTheme(theme).
 */

export const DEFAULT_THEME = Object.freeze({

  // ── Palette ──────────────────────────────────────────────────────────────
  bg:           '#0a0e1a',
  gridLine:     '#ffffff08',

  // ── Node colours by role ─────────────────────────────────────────────────
  // Each entry: { fill, stroke, textFill, nextBoxFill }
  nodeRoles: {
    default:   { fill: '#111827', stroke: '#334155', textFill: '#e2e8f0', nextBoxFill: '#1e293b' },
    head:      { fill: '#111827', stroke: '#6366f1', textFill: '#e2e8f0', nextBoxFill: '#1e293b' },
    tail:      { fill: '#111827', stroke: '#334155', textFill: '#e2e8f0', nextBoxFill: '#1e293b' },
    visiting:  { fill: '#1c1a08', stroke: '#eab308', textFill: '#fef9c3', nextBoxFill: '#2a2508' },
    comparing: { fill: '#1a1025', stroke: '#a855f7', textFill: '#f3e8ff', nextBoxFill: '#230f35' },
    inserting: { fill: '#052e16', stroke: '#22c55e', textFill: '#dcfce7', nextBoxFill: '#071f10' },
    deleting:  { fill: '#2d0a0a', stroke: '#ef4444', textFill: '#fee2e2', nextBoxFill: '#3d0f0f' },
    found:     { fill: '#0c1f3d', stroke: '#3b82f6', textFill: '#dbeafe', nextBoxFill: '#0d1f3f' },
    not_found: { fill: '#1c1410', stroke: '#f97316', textFill: '#fed7aa', nextBoxFill: '#251a10' },
    prev:      { fill: '#160d2b', stroke: '#8b5cf6', textFill: '#ede9fe', nextBoxFill: '#1e1030' },
    new:       { fill: '#052e16', stroke: '#4ade80', textFill: '#dcfce7', nextBoxFill: '#071f10' },
  },

  // ── Pointer/arrow colours by role ────────────────────────────────────────
  pointerRoles: {
    default:    { stroke: '#475569', dasharray: null },
    traversing: { stroke: '#eab308', dasharray: null },
    updating:   { stroke: '#22c55e', dasharray: null },
    new:        { stroke: '#4ade80', dasharray: null },
    breaking:   { stroke: '#ef4444', dasharray: '6 3' },
  },

  // ── Node geometry ────────────────────────────────────────────────────────
  nodeValueW:   96,    // width of the value section
  nodeNextW:    40,    // width of the next-pointer section
  nodeH:        52,    // total height
  nodeRx:        6,    // corner radius
  nodeGap:      80,    // horizontal gap between nodes (edge to edge)
  rowY:        200,    // vertical centre of all nodes

  // ── Typography ───────────────────────────────────────────────────────────
  valueFontSize:  18,
  labelFontSize:  10,
  fontFamily:     '"JetBrains Mono", "Fira Code", "Cascadia Code", monospace',

  // ── Arrows ───────────────────────────────────────────────────────────────
  arrowSize:      8,
  arrowStrokeW:   2,
  nullStubLen:   32,   // length of the null-pointer stub at the tail

  // ── Head/tail labels ─────────────────────────────────────────────────────
  labelOffsetY:  44,   // distance above node centre for "head"/"tail" labels

  // ── Transition timings (ms) ──────────────────────────────────────────────
  t: {
    nodeEnter:    350,
    nodeExit:     250,
    nodeMove:     450,
    colorChange:  300,
    arrowEnter:   300,
    arrowExit:    200,
    arrowReroute: 400,
    headLabel:    300,
  },
});