/**
 * LINKED LIST CORE — PUBLIC API
 *
 * This is the single import point for the data/operations layer.
 * The animation layer, narrative layer, and any tests should
 * import exclusively from here.
 *
 * ─── Quick Start ──────────────────────────────────────────────────────────────
 *
 *   import {
 *     fromArray, traverse, insertAtHead, deleteByValue, searchByValue, reverse
 *   } from './src/index.js';
 *
 *   const list  = fromArray([10, 20, 30, 40]);
 *   const steps = insertAtHead(list, 5);
 *
 *   // Each step has:
 *   //   step.state           — full list snapshot
 *   //   step.explanation     — human-readable text for the narrative layer
 *   //   step.highlights      — { nodes: [...], pointers: [...] } for the animation layer
 *   //   step.variables       — named pointer snapshot for the variable inspector
 *   //   step.pseudocodeLine  — which line of the operation's pseudocode is active
 *   //   step.isKeyStep       — true = worth pausing on in fast-forward mode
 *
 * ─── Layer Contract ───────────────────────────────────────────────────────────
 *
 *   INPUT  (data layer)   → ListState, built via createList() or fromArray()
 *   OUTPUT (this layer)   → Step[], one element per animation frame
 *   CONSUMER (next layer) → Playback Controller reads Step[] and fires events
 *                           to the Animation Layer and Narrative Layer
 */

// ─── Schema ──────────────────────────────────────────────────────────────────
export {
  createNode,
  createList,
  fromArray,
  toArray,
  getOrderedIds,
  getTailId,
  getNodeAtIndex,
  indexOfValue,
  validateList,
  NODE_ROLES,
  POINTER_ROLES,
  ACTIONS,
} from './schema/index.js';

// ─── Operations ──────────────────────────────────────────────────────────────
export {
  traverse,
  TRAVERSE_PSEUDOCODE,

  insertAtHead,
  insertAtTail,
  insertAtIndex,
  INSERT_AT_HEAD_PSEUDOCODE,
  INSERT_AT_TAIL_PSEUDOCODE,
  INSERT_AT_INDEX_PSEUDOCODE,

  deleteAtHead,
  deleteAtTail,
  deleteByValue,
  deleteAtIndex,
  DELETE_AT_HEAD_PSEUDOCODE,
  DELETE_AT_TAIL_PSEUDOCODE,
  DELETE_BY_VALUE_PSEUDOCODE,
  DELETE_AT_INDEX_PSEUDOCODE,

  searchByValue,
  SEARCH_PSEUDOCODE,

  reverse,
  REVERSE_PSEUDOCODE,
} from './operations/index.js';