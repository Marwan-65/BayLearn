// Shared utilities used by the algorithm modules.
// None of these touch the DOM or any animation layer --, pure data helpers.

let _counter = 0;

// Resets the ID counter. Useful between test runs so IDs are predictable.
function resetIdCounter() {
  _counter = 0;
}

// Generates a stable, unique node ID. The prefix helps with readability
// when you're staring at a step object during debugging.
function generateId(prefix = 'node') {
  _counter += 1;
  return `${prefix}_${_counter}`;
}

// Deep clone of a BTreeState. We only deal with plain objects/arrays/numbers
// so JSON round-trip is fine and keeps things simple. Don't reach for
// structuredClone unless you're targeting an older Node without it.
function cloneState(state) {
  return JSON.parse(JSON.stringify(state));
}

// Creates one Step object. The state is always deep-cloned so the caller
// can keep mutating the working state without corrupting the recorded step.
//
// Every field maps directly to the Step schema in section 3.2 of the spec.
function createStep({
  stepIndex,
  action,
  state,
  isKeyStep    = false,
  highlights   = {},
  explanation  = '',
  pseudocodeLine = null,
  variables    = {},
  meta         = {},
}) {
  return {
    stepIndex,
    action,
    isKeyStep,
    state: cloneState(state),
    highlights: {
      nodes: highlights.nodes || [],
      keys:  highlights.keys  || [],
      edges: highlights.edges || [],
    },
    explanation,
    pseudocodeLine,
    variables: { ...variables },
    meta: { ...meta },
  };
}

module.exports = { generateId, resetIdCounter, cloneState, createStep };