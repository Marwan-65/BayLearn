// tests ll operation wl uitilities for linked list
import assert from 'node:assert/strict';

import {
  createList, fromArray, toArray, getOrderedIds, validateList,
  traverse,
  insertAtHead, insertAtTail, insertAtIndex,
  deleteAtHead, deleteAtTail, deleteByValue, deleteAtIndex,
  searchByValue,
  reverse,
  ACTIONS,
} from '../index.js';

let passed = 0;
let failed = 0;

//di el tests di, hanet2aked en en el operations wl utilities elly fe linked list module byet5adem 3ala el schema el sah w byet2aked en el steps elly byerga3ha el operations di sah w consistent w kaman en el validateList byefham lama el list structure m4 sah w byerga3 errors mo3ayana.
function test(name, fn) {
  try {
    fn();
    console.log(`  PASS  ${name}`);
    passed++;
  } catch (err) {
    console.error(`  FAIL  ${name}`);
    console.error(`       ${err.message}`);
    failed++;
  }
}

function section(title) {
  console.log(`\n── ${title} ${'─'.repeat(50 - title.length)}`);
}

function finalState(steps) {
  return steps[steps.length - 1].state;
}

function lastAction(steps) {
  return steps[steps.length - 1].action;
}

function stepsHaveIncreasingIndices(steps) {
  return steps.every((s, i) => s.stepIndex === i);
}

// el section di byet2aked en el createList, fromArray, toArray byet5adem 3ala el schema el sah w byet2aked en el validateList byefham lama el list structure m4 sah w byerga3 errors mo3ayana.
section('Schema --, createList / fromArray / toArray');

test('createList returns empty list', () => {
  const l = createList();
  assert.equal(l.head, null);
  assert.equal(l.size, 0);
  assert.deepEqual(l.nodes, {});
});

test('fromArray builds correct structure', () => {
  const l = fromArray([1, 2, 3]);
  assert.deepEqual(toArray(l), [1, 2, 3]);
  assert.equal(l.size, 3);
});

test('fromArray with empty array returns empty list', () => {
  const l = fromArray([]);
  assert.equal(l.head, null);
  assert.equal(l.size, 0);
});

test('fromArray single element', () => {
  const l = fromArray([42]);
  assert.deepEqual(toArray(l), [42]);
  assert.equal(l.nodes[l.head].next, null);
});

test('validateList catches wrong size', () => {
  const l = fromArray([1, 2, 3]);
  l.size = 99;
  const { valid, errors } = validateList(l);
  assert.equal(valid, false);
  assert.ok(errors.some(e => e.includes('size')));
});

test('validateList catches broken next reference', () => {
  const l = fromArray([1, 2]);
  const headId = l.head;
  l.nodes[headId].next = 'nonexistent';
  const { valid } = validateList(l);
  assert.equal(valid, false);
});

test('validateList passes on valid list', () => {
  const { valid, errors } = validateList(fromArray([10, 20, 30]));
  assert.equal(valid, true);
  assert.equal(errors.length, 0);
});


// el section di byet2aked en el traverse, insertAtHead, insertAtTail, insertAtIndex, deleteAtHead, deleteAtTail, deleteByValue, deleteAtIndex, searchByValue, reverse byet5adem 3ala el schema el sah w byet2aked en el validateList byefham lama el list structure m4 sah w byerga3 errors mo3ayana, w kaman en el steps elly byerga3ha el operations di sah w consistent w kaman en kol step state howa snapshot immutable w m4 hayet2asar b ay mutation ba3d keda.
section('traverse');

test('traverse empty list ends immediately', () => {
  const steps = traverse(createList());
  assert.ok(steps.length >= 1);
  assert.equal(lastAction(steps), ACTIONS.OPERATION_COMPLETE);
});

test('traverse single node produces VISIT_NODE step', () => {
  const steps = traverse(fromArray([7]));
  const visit = steps.find(s => s.action === ACTIONS.VISIT_NODE);
  assert.ok(visit, 'should have a VISIT_NODE step');
});

test('traverse [1,2,3] visits all three nodes', () => {
  const steps = traverse(fromArray([1, 2, 3]));
  const visits = steps.filter(s => s.action === ACTIONS.VISIT_NODE);
  assert.equal(visits.length, 3);
});

test('traverse does not mutate the original list', () => {
  const list = fromArray([1, 2, 3]);
  traverse(list);
  assert.deepEqual(toArray(list), [1, 2, 3]);
});

test('traverse steps have correct increasing indices', () => {
  const steps = traverse(fromArray([1, 2, 3]));
  assert.ok(stepsHaveIncreasingIndices(steps));
});

test('traverse steps all carry variables.current', () => {
  const steps = traverse(fromArray([5, 10]));
  steps.slice(1).forEach(s => {
    assert.ok('current' in s.variables, `step ${s.stepIndex} missing variables.current`);
  });
});


// el section di byet2aked en el insertAtHead, insertAtTail, insertAtIndex, deleteAtHead, deleteAtTail, deleteByValue, deleteAtIndex, searchByValue, reverse byet5adem 3ala el schema el sah w byet2aked en el validateList byefham lama el list structure m4 sah w byerga3 errors mo3ayana, w kaman en el steps elly byerga3ha el operations di sah w consistent w kaman en kol step state howa snapshot immutable w m4 hayet2asar b ay mutation ba3d keda.
section('insertAtHead');

test('insertAtHead into empty list', () => {
  const steps = insertAtHead(createList(), 99);
  const fs = finalState(steps);
  assert.deepEqual(toArray(fs), [99]);
  assert.equal(fs.size, 1);
});

test('insertAtHead prepends to existing list', () => {
  const steps = insertAtHead(fromArray([2, 3, 4]), 1);
  assert.deepEqual(toArray(finalState(steps)), [1, 2, 3, 4]);
});

test('insertAtHead does not mutate original', () => {
  const list = fromArray([10, 20]);
  insertAtHead(list, 5);
  assert.deepEqual(toArray(list), [10, 20]);
});

test('insertAtHead has CREATE_NODE step', () => {
  const steps = insertAtHead(fromArray([1, 2]), 0);
  assert.ok(steps.some(s => s.action === ACTIONS.CREATE_NODE));
});

test('insertAtHead has SET_NEW_NEXT before UPDATE_HEAD', () => {
  const steps = insertAtHead(fromArray([1, 2]), 0);
  const setNextIdx  = steps.findIndex(s => s.action === ACTIONS.SET_NEW_NEXT);
  const updateHeadIdx = steps.findIndex(s => s.action === ACTIONS.UPDATE_HEAD);
  assert.ok(setNextIdx < updateHeadIdx, 'SET_NEW_NEXT must come before UPDATE_HEAD');
});

// el section di byet2aked en el insertAtTail byet5adem 3ala el schema el sah w byet2aked en el validateList byefham lama el list structure m4 sah w byerga3 errors mo3ayana, w kaman en el steps elly byerga3ha el insertAtTail sah w consistent w kaman en kol step state howa snapshot immutable w m4 hayet2asar b ay mutation ba3d keda.
section('insertAtTail');

test('insertAtTail into empty list', () => {
  const steps = insertAtTail(createList(), 5);
  assert.deepEqual(toArray(finalState(steps)), [5]);
});

test('insertAtTail appends to existing list', () => {
  const steps = insertAtTail(fromArray([1, 2, 3]), 4);
  assert.deepEqual(toArray(finalState(steps)), [1, 2, 3, 4]);
});

test('insertAtTail has ATTACH_TO_TAIL step', () => {
  const steps = insertAtTail(fromArray([1, 2]), 3);
  assert.ok(steps.some(s => s.action === ACTIONS.ATTACH_TO_TAIL));
});

// el section di byet2aked en el insertAtIndex byet5adem 3ala el schema el sah w byet2aked en el validateList byefham lama el list structure m4 sah w byerga3 errors mo3ayana, w kaman en el steps elly byerga3ha el insertAtIndex sah w consistent w kaman en kol step state howa snapshot immutable w m4 hayet2asar b ay mutation ba3d keda.
section('insertAtIndex');

test('insertAtIndex 0 behaves like insertAtHead', () => {
  const steps = insertAtIndex(fromArray([2, 3]), 1, 0);
  assert.deepEqual(toArray(finalState(steps)), [1, 2, 3]);
});

test('insertAtIndex at end behaves like insertAtTail', () => {
  const steps = insertAtIndex(fromArray([1, 2]), 3, 2);
  assert.deepEqual(toArray(finalState(steps)), [1, 2, 3]);
});

test('insertAtIndex in middle', () => {
  const steps = insertAtIndex(fromArray([1, 3, 4]), 2, 1);
  assert.deepEqual(toArray(finalState(steps)), [1, 2, 3, 4]);
});

test('insertAtIndex out of bounds returns INDEX_OUT_OF_BOUNDS', () => {
  const steps = insertAtIndex(fromArray([1, 2]), 99, 10);
  assert.equal(lastAction(steps), ACTIONS.INDEX_OUT_OF_BOUNDS);
});

// el section di byet2aked en el deleteAtHead, deleteAtTail, deleteByValue, deleteAtIndex byet5adem 3ala el schema el sah w byet2aked en el validateList byefham lama el list structure m4 sah w byerga3 errors mo3ayana, w kaman en el steps elly byerga3ha el deleteAtHead, deleteAtTail, deleteByValue, deleteAtIndex sah w consistent w kaman en kol step state howa snapshot immutable w m4 hayet2asar b ay mutation ba3d keda.
section('deleteAtHead');

test('deleteAtHead on empty list returns LIST_EMPTY', () => {
  const steps = deleteAtHead(createList());
  assert.ok(steps.some(s => s.action === ACTIONS.LIST_EMPTY));
});

test('deleteAtHead removes first element', () => {
  const steps = deleteAtHead(fromArray([1, 2, 3]));
  assert.deepEqual(toArray(finalState(steps)), [2, 3]);
});

test('deleteAtHead on single node leaves empty list', () => {
  const steps = deleteAtHead(fromArray([42]));
  const fs = finalState(steps);
  assert.equal(fs.head, null);
  assert.equal(fs.size, 0);
});

// el section di byet2aked en el deleteAtTail byet5adem 3ala el schema el sah w byet2aked en el validateList byefham lama el list structure m4 sah w byerga3 errors mo3ayana, w kaman en el steps elly byerga3ha el deleteAtTail sah w consistent w kaman en kol step state howa snapshot immutable w m4 hayet2asar b ay mutation ba3d keda.
section('deleteAtTail');

test('deleteAtTail removes last element', () => {
  const steps = deleteAtTail(fromArray([1, 2, 3]));
  assert.deepEqual(toArray(finalState(steps)), [1, 2]);
});

test('deleteAtTail on single node empties list', () => {
  const steps = deleteAtTail(fromArray([99]));
  assert.equal(finalState(steps).size, 0);
});

// el section di byet2aked en el deleteByValue byet5adem 3ala el schema el sah w byet2aked en el validateList byefham lama el list structure m4 sah w byerga3 errors mo3ayana, w kaman en el steps elly byerga3ha el deleteByValue sah w consistent w kaman en kol step state howa snapshot immutable w m4 hayet2asar b ay mutation ba3d keda.
section('deleteByValue');

test('deleteByValue removes matching head', () => {
  const steps = deleteByValue(fromArray([1, 2, 3]), 1);
  assert.deepEqual(toArray(finalState(steps)), [2, 3]);
});

test('deleteByValue removes middle node', () => {
  const steps = deleteByValue(fromArray([1, 2, 3]), 2);
  assert.deepEqual(toArray(finalState(steps)), [1, 3]);
});

test('deleteByValue removes tail node', () => {
  const steps = deleteByValue(fromArray([1, 2, 3]), 3);
  assert.deepEqual(toArray(finalState(steps)), [1, 2]);
});

test('deleteByValue not found returns VALUE_NOT_FOUND', () => {
  const steps = deleteByValue(fromArray([1, 2, 3]), 99);
  assert.equal(lastAction(steps), ACTIONS.VALUE_NOT_FOUND);
  assert.deepEqual(toArray(finalState(steps)), [1, 2, 3]);
});

// el section di byet2aked en el deleteAtIndex byet5adem 3ala el schema el sah w byet2aked en el validateList byefham lama el list structure m4 sah w byerga3 errors mo3ayana, w kaman en el steps elly byerga3ha el deleteAtIndex sah w consistent w kaman en kol step state howa snapshot immutable w m4 hayet2asar b ay mutation ba3d keda.
section('deleteAtIndex');

test('deleteAtIndex 0 removes head', () => {
  const steps = deleteAtIndex(fromArray([1, 2, 3]), 0);
  assert.deepEqual(toArray(finalState(steps)), [2, 3]);
});

test('deleteAtIndex middle', () => {
  const steps = deleteAtIndex(fromArray([1, 2, 3]), 1);
  assert.deepEqual(toArray(finalState(steps)), [1, 3]);
});

test('deleteAtIndex out of bounds', () => {
  const steps = deleteAtIndex(fromArray([1, 2]), 5);
  assert.equal(lastAction(steps), ACTIONS.INDEX_OUT_OF_BOUNDS);
});

// el section di byet2aked en el searchByValue byet5adem 3ala el schema el sah w byet2aked en el validateList byefham lama el list structure m4 sah w byerga3 errors mo3ayana, w kaman en el steps elly byerga3ha el searchByValue sah w consistent w kaman en kol step state howa snapshot immutable w m4 hayet2asar b ay mutation ba3d keda.
section('searchByValue');

test('searchByValue finds head', () => {
  const steps = searchByValue(fromArray([10, 20, 30]), 10);
  assert.equal(lastAction(steps), ACTIONS.VALUE_FOUND);
});

test('searchByValue finds tail', () => {
  const steps = searchByValue(fromArray([10, 20, 30]), 30);
  assert.equal(lastAction(steps), ACTIONS.VALUE_FOUND);
});

test('searchByValue not found', () => {
  const steps = searchByValue(fromArray([1, 2, 3]), 99);
  assert.equal(lastAction(steps), ACTIONS.VALUE_NOT_FOUND);
});

test('searchByValue empty list returns not found', () => {
  const steps = searchByValue(createList(), 5);
  assert.equal(lastAction(steps), ACTIONS.VALUE_NOT_FOUND);
});

test('searchByValue correct number of COMPARE_VALUE steps', () => {
  const steps = searchByValue(fromArray([10, 20, 30]), 30);
  const comparisons = steps.filter(s => s.action === ACTIONS.COMPARE_VALUE);
  assert.equal(comparisons.length, 3);
});

// el section di byet2aked en el reverse byet5adem 3ala el schema el sah w byet2aked en el validateList byefham lama el list structure m4 sah w byerga3 errors mo3ayana, w kaman en el steps elly byerga3ha el reverse sah w consistent w kaman en kol step state howa snapshot immutable w m4 hayet2asar b ay mutation ba3d keda.
section('reverse');

test('reverse empty list is no-op', () => {
  const steps = reverse(createList());
  assert.equal(finalState(steps).head, null);
});

test('reverse single node is no-op', () => {
  const steps = reverse(fromArray([1]));
  assert.deepEqual(toArray(finalState(steps)), [1]);
});

test('reverse [1,2,3] → [3,2,1]', () => {
  const steps = reverse(fromArray([1, 2, 3]));
  assert.deepEqual(toArray(finalState(steps)), [3, 2, 1]);
});

test('reverse [1,2,3,4,5] → [5,4,3,2,1]', () => {
  const steps = reverse(fromArray([1, 2, 3, 4, 5]));
  assert.deepEqual(toArray(finalState(steps)), [5, 4, 3, 2, 1]);
});

test('reverse does not mutate original', () => {
  const list = fromArray([1, 2, 3]);
  reverse(list);
  assert.deepEqual(toArray(list), [1, 2, 3]);
});

test('reverse has SAVE_NEXT steps equal to list length', () => {
  const list  = fromArray([1, 2, 3, 4]);
  const steps = reverse(list);
  const saveNextSteps = steps.filter(s => s.action === ACTIONS.SAVE_NEXT);
  assert.equal(saveNextSteps.length, list.size);
});

test('reverse has REVERSE_POINTER steps equal to list length', () => {
  const list  = fromArray([1, 2, 3]);
  const steps = reverse(list);
  const reverseSteps = steps.filter(s => s.action === ACTIONS.REVERSE_POINTER);
  assert.equal(reverseSteps.length, list.size);
});

test('each step state is independent (immutable snapshots)', () => {
  const steps = reverse(fromArray([1, 2, 3]));
  const step0HeadBefore = steps[0].state.head;
  steps[steps.length - 1].state.head = 'MUTATED';
  assert.equal(steps[0].state.head, step0HeadBefore);
});
console.log(`\n${'═'.repeat(55)}`);
console.log(`  ${passed + failed} tests   PASS ${passed} passed   FAIL ${failed} failed`);
console.log(`${'═'.repeat(55)}\n`);

if (failed > 0) process.exit(1);