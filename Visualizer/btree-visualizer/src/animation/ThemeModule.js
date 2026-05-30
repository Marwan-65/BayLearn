// ThemeModule.js
//
// Single source of truth for every visual constant the renderers and
// choreographer consume. Nothing is hardcoded anywhere else.
//
// Organised into four groups that mirror the spec:
//   COLOURS   --, semantic colour tokens (section 2.1)
//   FONTS     --, typeface choices and size scale (section 2.2)
//   LAYOUT    --, spacing and sizing (section 2.3)
//   TIMINGS   --, animation durations used by the Choreographer (section 6)

// ─── Colour palette (spec section 2.1) ───────────────────────────────────────

const COLOURS = {
  // Backgrounds
  BG_DEEP:      '#0f1117',
  BG_SURFACE:   '#1a1d27',
  BG_SURFACE2:  '#1e2130',
  BG_SURFACE3:  '#232638',

  // Borders
  BORDER:       '#2d3148',
  BORDER2:      '#3d4266',

  // Text
  TEXT:         '#e2e8f0',
  TEXT_MUTED:   '#64748b',
  TEXT_DIM:     '#334155',

  // Accent --, cyan (active/attention)
  GOLD:         '#06b6d4',
  GOLD_LIGHT:   '#22d3ee',
  GOLD_BG:      '#0c1e26',

  // Semantic
  GREEN:        '#10b981',
  GREEN_BG:     '#0a1f17',
  RED:          '#f43f5e',
  RED_BG:       '#1f0f18',
  BLUE:         '#3b82f6',
  BLUE_BG:      '#0f1629',
  PURPLE:       '#8b5cf6',
  PURPLE_BG:    '#160f2a',
  ORANGE:       '#f59e0b',
  ORANGE_BG:    '#1f1608',
};

// ─── Node role → visual style mappings ───────────────────────────────────────
//
// Each entry maps a NODE_ROLE constant to the stroke/fill the NodeRenderer
// should apply to the outer card rect. Using a lookup here keeps the renderer
// free of conditional chains.

const NODE_STYLES = {
  default:       { stroke: COLOURS.BORDER2,  fill: COLOURS.BG_SURFACE,  opacity: 1.0, strokeWidth: 1.5 },
  active:        { stroke: COLOURS.GOLD,      fill: COLOURS.GOLD_BG,     opacity: 1.0, strokeWidth: 2.5 },
  parent:        { stroke: COLOURS.GOLD,      fill: COLOURS.BG_SURFACE,  opacity: 0.7, strokeWidth: 1.5 },
  split_left:    { stroke: COLOURS.GREEN,     fill: COLOURS.GREEN_BG,    opacity: 1.0, strokeWidth: 2.0 },
  split_right:   { stroke: COLOURS.GREEN,     fill: COLOURS.GREEN_BG,    opacity: 1.0, strokeWidth: 2.0 },
  merge_target:  { stroke: COLOURS.BLUE,      fill: COLOURS.BLUE_BG,     opacity: 1.0, strokeWidth: 2.0 },
  merge_source:  { stroke: COLOURS.RED,       fill: COLOURS.RED_BG,      opacity: 1.0, strokeWidth: 2.0 },
  sibling_left:  { stroke: COLOURS.PURPLE,    fill: COLOURS.PURPLE_BG,   opacity: 1.0, strokeWidth: 2.0 },
  sibling_right: { stroke: COLOURS.PURPLE,    fill: COLOURS.PURPLE_BG,   opacity: 1.0, strokeWidth: 2.0 },
  overflow:      { stroke: COLOURS.RED,       fill: COLOURS.RED_BG,      opacity: 1.0, strokeWidth: 2.5 },
  underflow:     { stroke: COLOURS.ORANGE,    fill: COLOURS.ORANGE_BG,   opacity: 1.0, strokeWidth: 2.5 },
  dim:           { stroke: COLOURS.BORDER2,   fill: COLOURS.BG_SURFACE,  opacity: 0.25, strokeWidth: 1.0 },
};

// ─── Key role → slot fill colour ─────────────────────────────────────────────

const KEY_SLOT_FILLS = {
  default:     COLOURS.BG_SURFACE3,
  comparing:   COLOURS.GOLD_BG,
  found:       COLOURS.GREEN_BG,
  inserting:   COLOURS.GREEN_BG,
  deleting:    COLOURS.RED_BG,
  median:      COLOURS.GOLD_BG,
  promoting:   COLOURS.GOLD_BG,
  separator:   COLOURS.PURPLE_BG,
  predecessor: COLOURS.PURPLE_BG,
};

const KEY_SLOT_STROKES = {
  default:     COLOURS.BORDER,
  comparing:   COLOURS.GOLD_LIGHT,
  found:       COLOURS.GREEN,
  inserting:   COLOURS.GREEN,
  deleting:    COLOURS.RED,
  median:      COLOURS.GOLD,
  promoting:   COLOURS.GOLD,
  separator:   COLOURS.PURPLE,
  predecessor: COLOURS.PURPLE,
};

const KEY_TEXT_COLOURS = {
  default:     COLOURS.TEXT,
  comparing:   COLOURS.GOLD_LIGHT,
  found:       COLOURS.GREEN,
  inserting:   COLOURS.GREEN,
  deleting:    COLOURS.RED,
  median:      COLOURS.GOLD_LIGHT,
  promoting:   COLOURS.GOLD_LIGHT,
  separator:   COLOURS.PURPLE,
  predecessor: COLOURS.PURPLE,
};

// ─── Edge role → visual style ─────────────────────────────────────────────────

const EDGE_STYLES = {
  default:    { stroke: COLOURS.BORDER2, strokeWidth: 1.5, opacity: 0.6, dashArray: '' },
  path:       { stroke: COLOURS.GOLD,    strokeWidth: 2.5, opacity: 1.0, dashArray: '' },
  new:        { stroke: COLOURS.GREEN,   strokeWidth: 2.0, opacity: 1.0, dashArray: '6 3' },
  removing:   { stroke: COLOURS.RED,     strokeWidth: 1.5, opacity: 0.6, dashArray: '4 4' },
  rerouting:  { stroke: COLOURS.PURPLE,  strokeWidth: 2.0, opacity: 1.0, dashArray: '6 3' },
};

// ─── Pointer dot styles ───────────────────────────────────────────────────────

const DOT_STYLES = {
  default:    { fill: COLOURS.BORDER2, r: 3 },
  active:     { fill: COLOURS.GOLD,    r: 4 },
  path:       { fill: COLOURS.BLUE,    r: 4 },
};

// ─── Typography (spec section 2.2) ───────────────────────────────────────────

const FONTS = {
  UI_FONT:   '"Inter", "DM Sans", sans-serif',
  CODE_FONT: '"JetBrains Mono", "Fira Code", monospace',

  // Size + weight for each use-case (in px)
  KEY_VALUE:   { size: 20, weight: 700 },
  SLOT_LABEL:  { size:  9, weight: 400 },
  SECTION_TITLE: { size: 10, weight: 700 },
  EXPLANATION: { size: 13, weight: 400 },
  PSEUDOCODE:  { size: 11, weight: 400 },
  VARIABLE:    { size: 11, weight: 600 },
  BADGE:       { size: 10, weight: 600 },
};

// ─── Spacing & sizing (spec section 2.3) ─────────────────────────────────────

const LAYOUT = {
  SIDEBAR_WIDTH:     400,
  TOPBAR_HEIGHT:      56,

  SLOT_WIDTH:         52,
  SLOT_HEIGHT:        56,
  SLOT_GAP:            4,
  NODE_PADDING_X:     10,
  NODE_PADDING_Y:      8,
  NODE_CORNER_RADIUS: 10,
  NODE_SHADOW:        '0 4px 24px rgba(0,0,0,0.5)',

  LEVEL_SEPARATION:  120,
  SIBLING_SEPARATION: 24,

  EDGE_WIDTH_DEFAULT: 1.5,
  EDGE_WIDTH_ACTIVE:  2.5,

  SECTION_PADDING:    '16px 20px',
  CHIP_PADDING:       '4px 10px',

  // Badge offsets
  BADGE_GAP:          4,    // px above node top edge
  DOT_RADIUS:         3,    // child pointer dot radius (default)
  DOT_RADIUS_ACTIVE:  4,    // dot radius when highlighted
};

// ─── Animation timings (spec section 6) ──────────────────────────────────────
//
// All values in milliseconds. The Choreographer reads from this table.
// Modifying one value here automatically updates every animation that uses it.

const TIMINGS = {
  // General transitions
  HIGHLIGHT_FADE_IN:  200,
  HIGHLIGHT_FADE_OUT: 300,
  FOCUS_DIM:          300,
  FOCUS_RESTORE:      400,

  // Camera
  CAMERA_PAN_PER_LEVEL: 400,
  CAMERA_ZOOM_OUT:      400,
  CAMERA_FIT:           600,

  // Node transitions
  NODE_ENTER:      300,
  NODE_EXIT:       250,
  NODE_MOVE:       450,
  NODE_RESIZE:     300,

  // Key slot transitions
  KEY_ENTER:       200,
  KEY_EXIT:        200,
  KEY_SHIFT:       200,

  // Edge transitions
  EDGE_ENTER:      300,
  EDGE_EXIT:       200,
  EDGE_REROUTE:    200,

  // Split choreography (spec section 6.2 SPLIT_EXECUTE)
  SPLIT_CRACK:     200,
  SPLIT_FLOAT:     400,
  SPLIT_SETTLE:    500,
  SPLIT_EDGE_DRAW: 300,
  SPLIT_EDGE_STAGGER: 100,

  // Promote (PROMOTE_INTO_PARENT)
  PROMOTE_PARENT_HIGHLIGHT: 200,
  PROMOTE_EXPAND:           300,
  PROMOTE_SHIFT:            200,
  PROMOTE_ARRIVE:           250,
  PROMOTE_DOT_APPEAR:       200,

  // Borrow/rotate (BORROW_LEFT_ROTATE tumble)
  BORROW_HIGHLIGHT_SIBLING:  200,
  BORROW_HIGHLIGHT_PARENT:   200,
  BORROW_KEY_ARC:            500,
  BORROW_CONTRACT:           200,
  BORROW_EDGE_REROUTE:       200,

  // Merge gravity-pull
  MERGE_HIGHLIGHT:      200,
  MERGE_SEPARATOR_FALL: 400,
  MERGE_KEY_FLY:        350,
  MERGE_KEY_STAGGER:     80,
  MERGE_CHILDREN_ROUTE: 300,
  MERGE_SHELL_DISSOLVE: 300,
  MERGE_PARENT_UPDATE:  200,

  // Root shrink
  ROOT_SHRINK_PULSE:   300,
  ROOT_SHRINK_RISE:    600,
  ROOT_SHRINK_BADGE:   200,
  ROOT_SHRINK_SHIFT:   500,
};

// ─── Full theme object ────────────────────────────────────────────────────────
//
// createTheme() returns a single flat object that any module can import and
// use directly. It is a plain object --, no class, no getters, no magic.
//
// Pass overrides to createTheme() to create a custom theme:
//   const theme = createTheme({ GOLD: '#ffcc00' });

function createTheme(overrides = {}) {
  return {
    ...COLOURS,
    ...FONTS,
    ...LAYOUT,
    ...TIMINGS,
    NODE_STYLES:       { ...NODE_STYLES },
    KEY_SLOT_FILLS:    { ...KEY_SLOT_FILLS },
    KEY_SLOT_STROKES:  { ...KEY_SLOT_STROKES },
    KEY_TEXT_COLOURS:  { ...KEY_TEXT_COLOURS },
    EDGE_STYLES:       { ...EDGE_STYLES },
    DOT_STYLES:        { ...DOT_STYLES },
    ...overrides,
  };
}

module.exports = {
  createTheme,
  // Also export the raw groups for tests that want to verify individual tables
  COLOURS,
  FONTS,
  LAYOUT,
  TIMINGS,
  NODE_STYLES,
  KEY_SLOT_FILLS,
  KEY_SLOT_STROKES,
  KEY_TEXT_COLOURS,
  EDGE_STYLES,
  DOT_STYLES,
};