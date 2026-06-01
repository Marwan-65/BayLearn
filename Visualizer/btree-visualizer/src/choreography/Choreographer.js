// Choreographer.js
//
// The single place in the entire project where animation timing lives.
// Nothing else hardcodes delays or durations.
//
// Usage:
//   const plan = choreograph(prevStep, currentStep, theme);
//   nodeRenderer.render(currentStep, layout, plan);
//   floatLayer.execute(currentStep, layout, plan);
//
// choreograph() is a pure function --, same inputs always produce the same plan.
// The renderers and FloatLayer read the plan and apply it independently.

const { ACTIONS } = require('../core/constants');

// ─── Timing helpers ───────────────────────────────────────────────────────────

function ms(delay, duration) {
  return { delay, duration };
}

function zero() {
  return ms(0, 0);
}

// A plan where everything is instantaneous --, used for steps that need no
// transition (INITIAL_STATE, OPERATION_COMPLETE, etc.)
function staticPlan() {
  return {
    nodeEnter:     zero(),
    nodeExit:      zero(),
    nodeMove:      zero(),
    nodeResize:    zero(),
    keyEnter:      zero(),
    keyExit:       zero(),
    keyMove:       zero(),
    edgeEnter:     zero(),
    edgeExit:      zero(),
    edgeReroute:   zero(),
    highlightFade: zero(),
    focusChange:   zero(),
    cameraPan:     zero(),
  };
}

// ─── Main export ──────────────────────────────────────────────────────────────

/**
 * choreograph(prevStep, currentStep, theme) → ChoreographyPlan
 *
 * Reads the current step's action and returns a timing plan. The theme object
 * supplies the actual millisecond values from TIMINGS (see ThemeModule.js) so
 * there is no magic number in this file.
 *
 * @param {Step|null} prevStep     - the step before current (null on first step)
 * @param {Step}      currentStep  - the step being transitioned TO
 * @param {object}    theme        - full theme from createTheme()
 * @returns {ChoreographyPlan}
 */
function choreograph(prevStep, currentStep, theme) {
  const T = theme; // shorthand --, used heavily below
  const action = currentStep.action;

  switch (action) {

    // ── No-transition steps ────────────────────────────────────────────────
    case ACTIONS.INITIAL_STATE:
    case ACTIONS.OPERATION_COMPLETE:
      return staticPlan();

    // ── Search descent ────────────────────────────────────────────────────
    // Light, snappy transitions --, we visit a lot of nodes and we don't want
    // the student to get bored waiting.
    case ACTIONS.SEARCH_ENTER_NODE:
      return {
        ...staticPlan(),
        highlightFade: ms(0,   T.HIGHLIGHT_FADE_IN),
        focusChange:   ms(0,   T.FOCUS_DIM),
        cameraPan:     ms(0,   T.CAMERA_PAN_PER_LEVEL),
      };

    case ACTIONS.SEARCH_COMPARE_KEY:
    case ACTIONS.SEARCH_GO_RIGHT:
    case ACTIONS.SEARCH_GO_LEFT:
      return {
        ...staticPlan(),
        highlightFade: ms(0, T.HIGHLIGHT_FADE_IN),
      };

    case ACTIONS.SEARCH_DESCEND:
      return {
        ...staticPlan(),
        highlightFade: ms(0, T.HIGHLIGHT_FADE_IN),
        edgeReroute:   ms(0, T.EDGE_ENTER),
        cameraPan:     ms(0, T.CAMERA_PAN_PER_LEVEL),
      };

    case ACTIONS.SEARCH_FOUND:
    case ACTIONS.SEARCH_NOT_FOUND:
      return {
        ...staticPlan(),
        highlightFade: ms(0,   T.HIGHLIGHT_FADE_IN),
        focusChange:   ms(200, T.FOCUS_RESTORE),
      };

    // ── Insert --, descent ──────────────────────────────────────────────────
    case ACTIONS.INSERT_INTO_LEAF:
      // Spec section 6.2: new slot slides in from above, existing keys shift right
      return {
        ...staticPlan(),
        keyEnter:      ms(T.HIGHLIGHT_FADE_IN, 300),  // slide in after highlight
        keyMove:       ms(350, 250),                   // existing keys shift right
        highlightFade: ms(0,   T.HIGHLIGHT_FADE_IN),
        nodeResize:    ms(0,   T.NODE_RESIZE),
      };

    case ACTIONS.INSERT_SHIFT_KEYS:
      return {
        ...staticPlan(),
        keyMove:       ms(0, T.KEY_SHIFT),
        highlightFade: ms(0, T.HIGHLIGHT_FADE_IN),
      };

    // ── Overflow detection ────────────────────────────────────────────────
    case ACTIONS.OVERFLOW_DETECTED:
      return {
        ...staticPlan(),
        highlightFade: ms(0,   T.HIGHLIGHT_FADE_IN),
        focusChange:   ms(0,   T.FOCUS_DIM),
      };

    // ── Split sequence ──────────────────────────────────────────────────────
    case ACTIONS.SPLIT_PREPARE:
      // Highlight the median key before the crack
      return {
        ...staticPlan(),
        highlightFade: ms(0, T.HIGHLIGHT_FADE_IN),
        keyMove:       ms(0, 150),  // median scales up
        cameraPan:     ms(0, T.CAMERA_PAN_PER_LEVEL),
      };

    case ACTIONS.SPLIT_EXECUTE:
      // Left half shrinks (key exit + resize). The new right-half node is NOT
      // in the layout yet (it's orphaned until parent.children is updated at
      // PROMOTE_INTO_PARENT) so we don't animate nodeEnter here.
      return {
        ...staticPlan(),
        nodeResize:    ms(0,                T.SPLIT_FLOAT),  // left half narrows
        keyExit:       ms(0,                T.SPLIT_FLOAT),  // right-half keys leave
        highlightFade: ms(0, T.HIGHLIGHT_FADE_IN),
        focusChange:   ms(0, T.FOCUS_DIM),
        cameraPan:     ms(0, T.CAMERA_PAN_PER_LEVEL),
      };

    case ACTIONS.SPLIT_ROOT:
      // New root shell appears. Show it + the old root, then camera zooms to fit both.
      return {
        ...staticPlan(),
        nodeEnter:     ms(0,   T.NODE_ENTER),
        highlightFade: ms(0,   T.HIGHLIGHT_FADE_IN),
        cameraPan:     ms(0,   T.CAMERA_ZOOM_OUT),
      };

    case ACTIONS.PROMOTE_KEY:
      // Median key arc up to parent (handled by FloatLayer)
      return {
        ...staticPlan(),
        keyMove:       ms(0, 600),  // arc duration
        highlightFade: ms(0, T.HIGHLIGHT_FADE_IN),
      };

    case ACTIONS.PROMOTE_INTO_PARENT:
      // The new right-half node enters the layout here. Also: parent expands,
      // existing keys shift, promoted key lands. Camera fits the full new structure.
      return {
        ...staticPlan(),
        nodeEnter:     ms(0,                                             T.SPLIT_SETTLE),  // new right node appears
        nodeMove:      ms(0,                                             T.SPLIT_SETTLE),  // nodes settle into final pos
        nodeResize:    ms(T.PROMOTE_PARENT_HIGHLIGHT,                    T.PROMOTE_EXPAND),
        keyMove:       ms(T.PROMOTE_PARENT_HIGHLIGHT + T.PROMOTE_EXPAND - 100, T.PROMOTE_SHIFT),
        keyEnter:      ms(0,                                             T.SPLIT_SETTLE),  // right-half keys enter
        edgeEnter:     ms(T.SPLIT_SETTLE,                                T.SPLIT_EDGE_DRAW),
        highlightFade: ms(0, T.HIGHLIGHT_FADE_IN),
        cameraPan:     ms(0, T.CAMERA_FIT),
      };

    case ACTIONS.EDGE_REROUTE:
      return {
        ...staticPlan(),
        edgeEnter:     ms(0, T.SPLIT_EDGE_DRAW),
        edgeExit:      ms(0, T.EDGE_EXIT),
        edgeReroute:   ms(0, T.EDGE_REROUTE),
        highlightFade: ms(0, T.HIGHLIGHT_FADE_IN),
      };

    // ── Delete --, descent ──────────────────────────────────────────────────
    case ACTIONS.DELETE_FIND_KEY:
      return {
        ...staticPlan(),
        highlightFade: ms(0,   T.HIGHLIGHT_FADE_IN),
        focusChange:   ms(0,   T.FOCUS_DIM),
        cameraPan:     ms(0,   T.CAMERA_PAN_PER_LEVEL),
      };

    case ACTIONS.DELETE_FROM_LEAF:
      return {
        ...staticPlan(),
        keyExit:       ms(0,   T.KEY_EXIT),
        keyMove:       ms(100, T.KEY_SHIFT),  // remaining keys close the gap
        nodeResize:    ms(50,  T.NODE_RESIZE),
        highlightFade: ms(0,   T.HIGHLIGHT_FADE_IN),
      };

    case ACTIONS.DELETE_SHIFT_KEYS:
      return {
        ...staticPlan(),
        keyMove:       ms(0, T.KEY_SHIFT),
        highlightFade: ms(0, T.HIGHLIGHT_FADE_IN),
      };

    case ACTIONS.FIND_PREDECESSOR:
      return {
        ...staticPlan(),
        highlightFade: ms(0, T.HIGHLIGHT_FADE_IN),
        cameraPan:     ms(0, T.CAMERA_PAN_PER_LEVEL),
        edgeReroute:   ms(0, T.EDGE_ENTER),
      };

    case ACTIONS.REPLACE_WITH_PRED:
      // Old key fades out, predecessor value fades in at the same slot
      return {
        ...staticPlan(),
        keyExit:       ms(0,   T.KEY_EXIT),
        keyEnter:      ms(100, T.KEY_ENTER),
        highlightFade: ms(0,   T.HIGHLIGHT_FADE_IN),
      };

    // ── Underflow detection + strategy choice ─────────────────────────────
    case ACTIONS.UNDERFLOW_DETECTED:
      return {
        ...staticPlan(),
        highlightFade: ms(0, T.HIGHLIGHT_FADE_IN),
        focusChange:   ms(0, T.FOCUS_DIM),
      };

    case ACTIONS.FIX_CHOOSE_STRATEGY:
      return {
        ...staticPlan(),
        highlightFade: ms(0,   T.HIGHLIGHT_FADE_IN),
        focusChange:   ms(0,   T.FOCUS_DIM),
        cameraPan:     ms(0,   T.CAMERA_ZOOM_OUT), // pull back so student sees sibling too
      };

    // ── Borrow left (spec section 6.2 BORROW_LEFT_ROTATE tumble) ─────────
    case ACTIONS.BORROW_LEFT_PREPARE:
    case ACTIONS.BORROW_RIGHT_PREPARE:
      return {
        ...staticPlan(),
        highlightFade: ms(0, T.HIGHLIGHT_FADE_IN),
      };

    case ACTIONS.BORROW_LEFT_ROTATE:
    case ACTIONS.BORROW_RIGHT_ROTATE:
      // Spec: three keys trace a triangular arc simultaneously, then nodes resize
      return {
        ...staticPlan(),
        keyMove:       ms(T.BORROW_HIGHLIGHT_SIBLING + T.BORROW_HIGHLIGHT_PARENT, T.BORROW_KEY_ARC),
        nodeResize:    ms(T.BORROW_HIGHLIGHT_SIBLING + T.BORROW_HIGHLIGHT_PARENT + T.BORROW_KEY_ARC, T.BORROW_CONTRACT),
        edgeReroute:   ms(T.BORROW_HIGHLIGHT_SIBLING + T.BORROW_HIGHLIGHT_PARENT + T.BORROW_KEY_ARC + T.BORROW_CONTRACT, T.BORROW_EDGE_REROUTE),
        highlightFade: ms(0, T.HIGHLIGHT_FADE_IN),
      };

    // ── Merge sequence (spec section 6.2 MERGE_EXECUTE gravity-pull) ─────
    case ACTIONS.MERGE_PREPARE:
      return {
        ...staticPlan(),
        highlightFade: ms(0, T.MERGE_HIGHLIGHT),
        focusChange:   ms(0, T.FOCUS_DIM),
        cameraPan:     ms(0, T.CAMERA_ZOOM_OUT),
      };

    case ACTIONS.MERGE_PULL_SEPARATOR:
      // Separator key falls from parent into left node (FloatLayer handles the arc)
      return {
        ...staticPlan(),
        keyMove:       ms(0,   T.MERGE_SEPARATOR_FALL),
        keyEnter:      ms(T.MERGE_SEPARATOR_FALL, T.KEY_ENTER),
        highlightFade: ms(0,   T.MERGE_HIGHLIGHT),
      };

    case ACTIONS.MERGE_ABSORB_KEYS:
      // Right node's keys fly leftward, staggered --, FloatLayer handles the arcs
      return {
        ...staticPlan(),
        keyMove:       ms(0, T.MERGE_KEY_FLY),
        nodeResize:    ms(T.MERGE_KEY_FLY, T.NODE_RESIZE),
        highlightFade: ms(0, T.MERGE_HIGHLIGHT),
      };

    case ACTIONS.MERGE_ABSORB_CHILDREN:
      return {
        ...staticPlan(),
        edgeReroute:   ms(0, T.MERGE_CHILDREN_ROUTE),
        highlightFade: ms(0, T.MERGE_HIGHLIGHT),
      };

    case ACTIONS.MERGE_REMOVE_NODE:
      // Right node shell dissolves
      return {
        ...staticPlan(),
        nodeExit:      ms(0, T.MERGE_SHELL_DISSOLVE),
        edgeExit:      ms(0, T.EDGE_EXIT),
        highlightFade: ms(0, T.MERGE_HIGHLIGHT),
      };

    case ACTIONS.MERGE_UPDATE_PARENT:
      return {
        ...staticPlan(),
        keyExit:       ms(0,   T.MERGE_PARENT_UPDATE),
        nodeResize:    ms(0,   T.NODE_RESIZE),
        edgeExit:      ms(100, T.EDGE_EXIT),
        highlightFade: ms(0,   T.MERGE_HIGHLIGHT),
      };

    // ── Root shrink ───────────────────────────────────────────────────────
    case ACTIONS.ROOT_SHRINK:
      // Spec section 6.2: child rises one level, old root fades
      return {
        ...staticPlan(),
        nodeExit:      ms(0,                             T.ROOT_SHRINK_PULSE),
        nodeMove:      ms(T.ROOT_SHRINK_PULSE,           T.ROOT_SHRINK_RISE),
        nodeEnter:     ms(0,                             T.NODE_ENTER),
        edgeExit:      ms(0,                             T.EDGE_EXIT),
        edgeEnter:     ms(T.ROOT_SHRINK_PULSE,           T.SPLIT_EDGE_DRAW),
        highlightFade: ms(0,                             T.HIGHLIGHT_FADE_IN),
        cameraPan:     ms(T.ROOT_SHRINK_PULSE,           T.CAMERA_FIT),
      };

    // ── Fallback --, any action not explicitly listed above gets a quick
    //    highlight-only transition so nothing looks broken
    default:
      return {
        ...staticPlan(),
        highlightFade: ms(0, T.HIGHLIGHT_FADE_IN),
      };
  }
}

module.exports = { choreograph, staticPlan };