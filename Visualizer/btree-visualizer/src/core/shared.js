// these are the shared utitilities used by the allgorithm modules
//they have no relationn to UI, only data

let _counter = 0;

//reset the id counter, useful for testing and in between runs
function resetIdCounter() {
  _counter = 0;
}

// generate a stable and unique id,
// prefix is optional abut helps with dbugging like node_1, root_2
function generateId(prefix = 'node') {
  _counter += 1;
  return `${prefix}_${_counter}`;
}

//this is how we clone a json object
//json parse first turns the object to a string, and then stringify turns it back into an object, but with a new reference in memory
//we do this so when we create a step it is frozen and will not be affected by any changes we make to the state
function cloneState(state) {
  return JSON.parse(JSON.stringify(state));
}


//this function is how we create the step json object,
//we deep clone the state always so that we can mutate the working state as we like without caring about the recorded step

function createStep({
  stepIndex, //the index if the step in sequence starting from 0
  action, //the action describing what happened in this step
  state, // the current state which we will clone
  isKeyStep    = false, //used for UI
  highlights   = {}, //optional and also helps in UI
  explanation  = '', // 
  pseudocodeLine = null,// the line number of the pseudocode to highlight, if we will highlight
  variables    = {},// what variables to include. used in UI
  meta         = {},//any other metadata
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