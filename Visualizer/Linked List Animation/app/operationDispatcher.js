import {
  traverse,
  insertAtHead,
  insertAtTail,
  insertAtIndex,
  deleteAtHead,
  deleteAtTail,
  deleteByValue,
  deleteAtIndex,
  searchByValue,
  reverse,
} from '../index.js';

/**
 * Builds animation steps for a selected operation.
 *
 * @param {string} op
 * @param {object} list
 * @param {Array<*>} params
 * @returns {Array<object>}
 */
export function buildSteps(op, list, params = []) {
  const [value, index] = params;

  const dispatch = {
    traverse:      () => traverse(list),
    insertAtHead:  () => insertAtHead(list, value),
    insertAtTail:  () => insertAtTail(list, value),
    insertAtIndex: () => insertAtIndex(list, value, index),
    deleteAtHead:  () => deleteAtHead(list),
    deleteAtTail:  () => deleteAtTail(list),
    deleteByValue: () => deleteByValue(list, value),
    deleteAtIndex: () => deleteAtIndex(list, index),
    searchByValue: () => searchByValue(list, value),
    reverse:       () => reverse(list),
  };

  return dispatch[op]?.() ?? [];
}
