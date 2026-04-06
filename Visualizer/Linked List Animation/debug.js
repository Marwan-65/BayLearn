import { fromArray, insertAtHead, INSERT_AT_HEAD_PSEUDOCODE, DELETE_AT_HEAD_PSEUDOCODE, deleteAtHead } from './index.js';

const list  = fromArray([2, 3, 4]);
const steps = insertAtHead(list, 1);
const steps2= deleteAtHead(list)

steps.forEach(step => {
  console.log(`\n─── Step ${step.stepIndex} ───`);
  console.log(`  Action:      ${step.action}`);
  console.log(`  Pseudocode:  line ${step.pseudocodeLine} → "${INSERT_AT_HEAD_PSEUDOCODE[step.pseudocodeLine]}"`);
  console.log(`  Explanation: ${step.explanation}`);
  console.log(`  List:        ${JSON.stringify(Object.values(step.state.nodes).map(n => n.value))}`);
  console.log(`  Variables:   ${JSON.stringify(step.variables)}`);
  console.log(`  Highlights:  ${JSON.stringify(step.highlights)}`);
  console.log(`  isKeyStep:   ${step.isKeyStep}`);
});
steps2.forEach(step => {
  console.log(`\n─── Step ${step.stepIndex} ───`);
  console.log(`  Action:      ${step.action}`);
  console.log(`  Pseudocode:  line ${step.pseudocodeLine} → "${DELETE_AT_HEAD_PSEUDOCODE[step.pseudocodeLine]}"`);
  console.log(`  Explanation: ${step.explanation}`);
  console.log(`  List:        ${JSON.stringify(Object.values(step.state.nodes).map(n => n.value))}`);
  console.log(`  Variables:   ${JSON.stringify(step.variables)}`);
  console.log(`  Highlights:  ${JSON.stringify(step.highlights)}`);
  console.log(`  isKeyStep:   ${step.isKeyStep}`);
});