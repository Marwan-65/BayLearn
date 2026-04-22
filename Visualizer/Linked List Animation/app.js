/**
 * APP.JS — WIRING LOGIC
 *
 * This file is the only place in the entire codebase where all three layers
 * (Animation, Narrative, Playback) are imported and connected together.
 *
 * Its job is narrow: parse the user's input, build the step sequence,
 * instantiate the controller, and wire the two layers to it.
 *
 * It contains NO rendering logic, NO animation logic, NO narrative logic.
 * If any of those things change, this file does not need to change.
 *
 * ─── File location ────────────────────────────────────────────────────────
 * This file lives at the PROJECT ROOT, alongside index.html.
 *
 *   linked-list-core/
 *     index.html          ← HTML shell
 *     app.js              ← YOU ARE HERE
 *     index.js            ← public core barrel
 *     schema/
 *     operations/
 *     playback/
 *     animation/
 *     narrative/
 */

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

// ─── Module-level singletons ──────────────────────────────────────────────────
// AnimationLayer and NarrativeLayer are created ONCE at startup and reused
// across all operations. Only the PlaybackController is recreated per operation.

let animLayer  = null;
let narrLayer  = null;
let controller = null;

let scenario = null;
let scenarioIndex = 0;
let scenarioWorkingList = null;
let scenarioWorkingListText = null;

const SCENARIO_FILE = './linked-list-sequence.json';

// ─── Operation dispatcher ─────────────────────────────────────────────────────

const OPS_NEEDING_VALUE = new Set([
  'insertAtHead', 'insertAtTail', 'insertAtIndex',
  'deleteByValue', 'searchByValue',
]);
const OPS_NEEDING_INDEX = new Set(['insertAtIndex', 'deleteAtIndex']);

/**
 * Map an operation key + parameters to the correct operation function call.
 * Returns a Step[] array. Pure — no side effects.
 *
 * @param {string}    op
 * @param {ListState} list
 * @param {*}         value   numeric or string value param
 * @param {number}    index   numeric index param
 * @returns {Step[]}
 */
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

// ─── Core run function ────────────────────────────────────────────────────────

/**
 * Called every time the user clicks "Run".
 * Reads the current UI state, builds a step sequence, and starts playback.
 */
function runOperation() {
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

  // 2. Build the step sequence (pure data, no rendering)
  const steps = buildSteps(op, list, value, index);
  if (!steps.length) return;

  // In scenario mode, treat the resulting list as the next input seed.
  syncScenarioAfterRun(steps);

  // 3. Pre-flight: load the correct pseudocode + complexity into the narrative
  //    layer BEFORE the controller fires its first event.
  narrLayer.loadOperation(op);

  // 4. Destroy the old controller to stop any running timers and clear
  //    old event listeners. Skipping this would double-fire events.
  if (controller) controller.destroy();

  // Reset animation history so the next operation is rendered as a fresh run.
  if (animLayer) animLayer._prev = null;

  controller = new PlaybackController(steps, {
    speed:            currentSpeed(),
    pauseOnKeySteps:  true,
  });

  // 5. Wire the two layers to the controller.
  //    Each layer receives the same Step object; they read different fields.
  controller.on('frame',     step => animLayer.render(step));
  controller.on('narrative', step => narrLayer.update(step));
  controller.on('statusChange', updatePlaybackUI);
  controller.on('complete',  () => updatePlaybackUI({
    status:       'done',
    currentIndex: controller.currentIndex,
    totalSteps:   controller.totalSteps,
    progress:     1,
  }));

  // 6. Render the first frame immediately — before the user presses play.
  //    Without this the canvas is blank on load.
  animLayer.render(steps[0]);
  narrLayer.update(steps[0]);
  resetView(steps[0].state);

  // 7. Sync the playback UI chrome (progress bar, step counter, play button)
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
  const nextList = toArray(lastStep.state);
  const nextListText = nextList.join(', ');
  document.getElementById('input-list').value = nextListText;
  scenarioWorkingListText = nextListText;

  scenarioIndex += 1;
  if (scenarioIndex < scenario.operations.length) {
    applyScenarioStep(scenario.operations[scenarioIndex]);
  }
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

// ─── Playback UI chrome ───────────────────────────────────────────────────────
// These functions update the HTML controls (progress bar, buttons, etc.)
// They are driven by statusChange events from the controller.

function updatePlaybackUI({ status, currentIndex, totalSteps, progress }) {
  document.getElementById('status-dot').className  = status;
  document.getElementById('status-text').textContent = status;
  document.getElementById('progress-fill').style.width = `${(progress * 100).toFixed(1)}%`;
  document.getElementById('step-counter').textContent  = `${currentIndex + 1} / ${totalSteps}`;
  document.getElementById('btn-play').textContent = status === 'playing' ? '⏸' : '▶';

  // Flash the key-step banner when playback auto-pauses on a key step
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

// ─── SVG viewport reset ───────────────────────────────────────────────────────
// Called once after loading new steps to frame all nodes in view.

function resetView(state) {
  // AnimationLayer exposes a resetView method that computes the
  // bounding box of all nodes and sets the D3 zoom transform accordingly.
  if (animLayer?.resetView) animLayer.resetView(state);
}

// ─── Op-select: show/hide params ─────────────────────────────────────────────

function syncParamVisibility() {
  const op = document.getElementById('op-select').value;
  document.getElementById('param-value').style.display =
    OPS_NEEDING_VALUE.has(op) ? '' : 'none';
  document.getElementById('param-index').style.display =
    OPS_NEEDING_INDEX.has(op) ? '' : 'none';
}

// ─── Bootstrap ───────────────────────────────────────────────────────────────

window.addEventListener('load', async () => {
  // Instantiate long-lived singletons
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

  // Attach event listeners to the HTML controls
  document.getElementById('op-select')
    .addEventListener('change', syncParamVisibility);

  syncParamVisibility();

  await loadScenario();

  // Keep the original behavior for manual mode only.
  if (!scenario) runOperation();
});

// ─── Expose to HTML onclick attributes ───────────────────────────────────────
// index.html buttons use onclick="..." which needs these on window.

window.runOperation  = runOperation;
window.scrubTo       = scrubTo;
window.onSpeedChange = onSpeedChange;

// Playback button handlers — proxy to controller so HTML doesn't need to
// know controller exists
window.ctrlPlay        = () => controller?.togglePlay();
window.ctrlStepFwd     = () => controller?.stepForward();
window.ctrlStepBack    = () => controller?.stepBack();
window.ctrlRewind      = () => controller?.rewind();
window.ctrlJumpEnd     = () => controller?.jumpToEnd();
window.ctrlNextKey     = () => controller?.nextKeyStep();
window.ctrlPrevKey     = () => controller?.prevKeyStep();