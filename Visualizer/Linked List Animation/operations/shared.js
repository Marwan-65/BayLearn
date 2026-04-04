/**
 * OPERATIONS / SHARED UTILITIES
 *
 * Helpers used by every operation module.
 * Nothing here is exported from the public API — it is internal plumbing.
 */

// ─── State Cloning ────────────────────────────────────────────────────────────

/**
 * Deep-clones a list state.
 *
 * Each Step stores a snapshot of the list at that moment. We clone via
 * JSON round-trip because list states only contain plain serialisable values
 * (strings, numbers, nulls, plain objects). This keeps the implementation
 * simple and avoids accidental shared references between steps.
 *
 * @param {ListState} state
 * @returns {ListState}
 */
export function cloneState(state) {
  return JSON.parse(JSON.stringify(state));
}

// ─── ID Generation ────────────────────────────────────────────────────────────

/**
 * Generates the next available node ID and increments the counter.
 * Mutates list._nextId — call this on your working copy, not the original.
 *
 * @param {ListState} list  (working copy)
 * @returns {string}        e.g. "n3"
 */
export function generateId(list) {
  const id = `n${list._nextId}`;
  list._nextId += 1;
  return id;
}

// ─── Step Builder ─────────────────────────────────────────────────────────────

/**
 * Builds a single animation step.
 *
 * The state is deep-cloned internally so the caller can keep mutating their
 * working copy between steps without corrupting earlier snapshots.
 *
 * @param {object} params
 * @param {number}          params.stepIndex        - Ordinal position in the steps array
 * @param {ListState}       params.state            - Working list state (will be cloned)
 * @param {string}          params.action           - Machine-readable action type (from ACTIONS)
 * @param {string}          params.explanation      - Human-readable explanation for the student
 * @param {NodeHighlight[]} [params.nodeHighlights]     - Which nodes to highlight and how
 * @param {PointerHighlight[]} [params.pointerHighlights] - Which pointers to highlight and how
 * @param {object}          [params.variables]      - Named pointer snapshot { name: nodeId|null }
 * @param {number|null}     [params.pseudocodeLine] - 0-based index into the operation's PSEUDOCODE array
 * @param {boolean}         [params.isKeyStep]      - true = conceptually important (shown in fast-forward mode)
 *
 * @returns {Step}
 */
export function createStep({
  stepIndex,
  state,
  action,
  explanation,
  nodeHighlights    = [],
  pointerHighlights = [],
  variables         = {},
  pseudocodeLine    = null,
  isKeyStep         = false,
}) {
  return {
    stepIndex,
    state:    cloneState(state),   // snapshot — immutable after creation
    action,
    explanation,
    highlights: {
      nodes:    nodeHighlights,
      pointers: pointerHighlights,
    },
    variables,
    pseudocodeLine,
    isKeyStep,
  };
}