
import {
  fromArray,
  toArray,
  traverse,
  insertAtHead, insertAtTail, insertAtIndex,
  deleteAtHead, deleteAtTail, deleteByValue, deleteAtIndex,
  searchByValue,
  reverse,
} from './index.js';

import { PlaybackController } from './playback/PlaybackController.js';
import { AnimationLayer }     from './animation/Animationlayer.js';
import { NarrativeLayer }     from './narrative/NarrativeLayer.js';


let animLayer  = null;
let narrLayer  = null;
let controller = null;

let scenario = null;
let scenarioIndex = 0;
let scenarioWorkingList = null;
let scenarioWorkingListText = null;

const SCENARIO_FILE = './linked-list-sequence.json';


const OPS_NEEDING_VALUE = new Set([
  'insertAtHead', 'insertAtTail', 'insertAtIndex',
  'deleteByValue', 'searchByValue',
]);
const OPS_NEEDING_INDEX = new Set(['insertAtIndex', 'deleteAtIndex']);


function buildSteps(op, list, value, index) {
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


function runOperation() {
  if (scenario && scenarioIndex < scenario.operations.length) {
    applyScenarioStep(scenario.operations[scenarioIndex]);
  }
  if (scenario && scenarioWorkingList) {
    const listText = toArray(scenarioWorkingList).join(', ');
    document.getElementById('input-list').value = listText;
    scenarioWorkingListText = listText;
  }

  // 1. Parse inputs
  const rawList = document.getElementById('input-list').value;
  const values  = rawList
    .split(',')
    .map(s => s.trim())
    .filter(Boolean)
    .map(s => (isNaN(s) ? s : Number(s)));

  const normalizedRawList = normalizeListText(rawList);
  const useScenarioState = Boolean(
    scenario && scenarioWorkingList && scenarioWorkingListText === normalizedRawList
  );

  const list  = useScenarioState ? scenarioWorkingList : fromArray(values);
  const op    = document.getElementById('op-select').value;
  const value = (() => {
    const v = document.getElementById('param-value').value;
    return isNaN(v) ? v : Number(v);
  })();
  const index = Number(document.getElementById('param-index').value);

  const steps = buildSteps(op, list, value, index);
  if (!steps.length) return;

  syncScenarioAfterRun(steps);


  narrLayer.loadOperation(op);


  if (controller) controller.destroy();

  if (animLayer) animLayer._prev = null;

  controller = new PlaybackController(steps, {
    speed:            currentSpeed(),
    pauseOnKeySteps:  true,
  });


  controller.on('frame',     step => animLayer.render(step));
  controller.on('narrative', step => narrLayer.update(step));
  controller.on('statusChange', updatePlaybackUI);
  controller.on('complete',  () => updatePlaybackUI({
    status:       'done',
    currentIndex: controller.currentIndex,
    totalSteps:   controller.totalSteps,
    progress:     1,
  }));


  animLayer.render(steps[0]);
  narrLayer.update(steps[0]);
  resetView(steps[0].state);

  updatePlaybackUI({
    status:       'idle',
    currentIndex: 0,
    totalSteps:   steps.length,
    progress:     0,
  });
}

function applyScenarioStep(step) {
  if (!step || typeof step !== 'object') return;

  document.getElementById('op-select').value = step.op ?? 'traverse';

  if ('value' in step) {
    document.getElementById('param-value').value = step.value;
  }

  if ('index' in step) {
    document.getElementById('param-index').value = step.index;
  }

  syncParamVisibility();
}

function prefillFromScenarioStart() {
  if (!scenario) return;

  const listText = scenario.initialList.map(v => String(v)).join(', ');
  document.getElementById('input-list').value = listText;
  scenarioWorkingList = fromArray(scenario.initialList);
  scenarioWorkingListText = listText;

  scenarioIndex = 0;
  applyScenarioStep(scenario.operations[scenarioIndex]);
}

function syncScenarioAfterRun(steps) {
  if (!scenario || !Array.isArray(steps) || steps.length === 0) return;

  const lastStep = steps[steps.length - 1];
  scenarioWorkingList = lastStep.state;
  scenarioWorkingListText = toArray(lastStep.state).join(', ');

  scenarioIndex += 1;
}

function normalizeListText(text) {
  return text
    .split(',')
    .map(part => part.trim())
    .filter(Boolean)
    .join(', ');
}

async function loadScenario() {
  try {
    const res = await fetch(SCENARIO_FILE);
    if (!res.ok) return;

    const parsed = await res.json();
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return;
    if (!Array.isArray(parsed.initialList) || !Array.isArray(parsed.operations)) return;
    if (parsed.operations.length === 0) return;

    const hasInvalidOp = parsed.operations.some(item => !item || typeof item.op !== 'string');
    if (hasInvalidOp) return;

    scenario = parsed;
    prefillFromScenarioStart();
  } catch {
    // Scenario mode is optional. If loading fails, keep normal manual mode.
  }
}

function updatePlaybackUI({ status, currentIndex, totalSteps, progress }) {
  document.getElementById('status-dot').className  = status;
  document.getElementById('status-text').textContent = status;
  document.getElementById('progress-fill').style.width = `${(progress * 100).toFixed(1)}%`;
  document.getElementById('step-counter').textContent  = `${currentIndex + 1} / ${totalSteps}`;
  document.getElementById('btn-play').textContent = status === 'playing' ? '⏸' : '▶';

  const step   = controller?.currentStep;
  const banner = document.getElementById('keystep-banner');
  if (step?.isKeyStep && status === 'paused') {
    banner.classList.add('show');
    setTimeout(() => banner.classList.remove('show'), 1800);
  }
}

function scrubTo(event) {
  if (!controller) return;
  const track = document.getElementById('progress-track');
  const rect  = track.getBoundingClientRect();
  const frac  = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
  controller.jumpTo(Math.round(frac * (controller.totalSteps - 1)));
}

function currentSpeed() {
  return Number(document.getElementById('speed-range').value) * 0.4;
}

function onSpeedChange(val) {
  const speed = Number(val) * 0.4;
  document.getElementById('speed-label').textContent = `${speed.toFixed(1)}×`;
  if (controller) controller.setSpeed(speed);
}


function resetView(state) {

  if (animLayer?.resetView) animLayer.resetView(state);
}


function syncParamVisibility() {
  const op = document.getElementById('op-select').value;
  document.getElementById('param-value').style.display =
    OPS_NEEDING_VALUE.has(op) ? '' : 'none';
  document.getElementById('param-index').style.display =
    OPS_NEEDING_INDEX.has(op) ? '' : 'none';
}


window.addEventListener('load', async () => {
  animLayer = new AnimationLayer(
    document.getElementById('viz-svg'),
    window.d3   // D3 loaded via <script> tag in index.html, available as window.d3
  );

  narrLayer = new NarrativeLayer({
    complexityEl:  document.getElementById('complexity-panel'),
    codeEl:        document.getElementById('code-lines'),
    explanationEl: document.getElementById('explanation-text'),
    varListEl:     document.getElementById('var-list'),
  });

  document.getElementById('op-select')
    .addEventListener('change', syncParamVisibility);

  syncParamVisibility();

  const params = new URLSearchParams(window.location.search);
  const runId = params.get('run_id');

  if (runId) {
    try {
      const apiBase = 'http://localhost:8010';
      const res = await fetch(`${apiBase}/v1/runs/${runId}/payload`);
      if (res.ok) {
        const payload = await res.json();
        const extraction = payload.extraction;
        // Convert extraction to the visualizer scenario format if needed.
        if (extraction) {

          if (extraction.initialList || extraction.operations) {
            scenario = {
              initialList: extraction.initialList || extraction.initial_list || [],
              operations: extraction.operations || extraction.operations || [],
            };
          } else {
            scenario = {
              initialList: extraction.initial_list || [],
              operations: (extraction.operations || []).map(op => ({
                op: op.op,
                value: ('value' in op) ? op.value : null,
                index: ('index' in op) ? op.index : null,
              })),
            };
          }
        }
      }
    } catch (e) {
      console.warn('Failed to load run payload:', e);
    }
  }

  await loadScenario();

  if (!scenario) runOperation();
  else {
    prefillFromScenarioStart();
    runOperation();
  }
});

window.runOperation  = runOperation;
window.scrubTo       = scrubTo;
window.onSpeedChange = onSpeedChange;


window.ctrlPlay        = () => controller?.togglePlay();
window.ctrlStepFwd     = () => controller?.stepForward();
window.ctrlStepBack    = () => controller?.stepBack();
window.ctrlRewind      = () => controller?.rewind();
window.ctrlJumpEnd     = () => controller?.jumpToEnd();
window.ctrlNextKey     = () => controller?.nextKeyStep();
window.ctrlPrevKey     = () => controller?.prevKeyStep();