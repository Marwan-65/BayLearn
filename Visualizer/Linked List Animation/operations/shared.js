// da shared internal file mafeesh 7aga bt get exported lbarra el module

//this is how we clone a json object
//json parse first turns the object to a string, and then stringify turns it back into an object, but with a new reference in memory
//we do this so when we create a step it is frozen and will not be affected by any changes we make to the state
export function cloneState(state) {
  return JSON.parse(JSON.stringify(state));
}

//generate le next available node id w zawed el counter, by mutate el list._nextId, fa et2aked enak btest5dem el working copy m4 el original
export function generateId(list) {
  const id = `n${list._nextId}`;
  list._nextId += 1;
  return id;
}


//by return step object, which includes a deep-cloned snapshot of the state, za2ed el metadata about what to highlight and how to explain the step.
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
    state:    cloneState(state),   // snapshot --, immutable after creation
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