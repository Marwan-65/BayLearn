// app.js
//
// Wiring only. No algorithm logic, no rendering, no layout math.
// This file connects all layers and handles UI events.

'use strict';

const d3 = require('d3');

const { AnimationLayer }     = require('./src/animation/AnimationLayer');
const { NarrativeLayer }     = require('./src/narrative/NarrativeLayer');
const { PlaybackController } = require('./src/playback/PlaybackController');
const { createTree, validate } = require('./src/core/BTree');
const { resetIdCounter }     = require('./src/core/shared');
const { search }             = require('./src/core/search');
const { insert }             = require('./src/core/insert');
const { deleteKey }          = require('./src/core/delete');
const { SCENARIOS, SCENARIO_MAP } = require('./src/scenarios/scenarios');
const { ScenarioRunner }     = require('./src/scenarios/ScenarioRunner');
const { createTheme }        = require('./src/animation/ThemeModule');
const { choreograph }        = require('./src/choreography/Choreographer');

// ─── App state ────────────────────────────────────────────────────────────────

let anim      = null;
let narr      = null;
let ctrl      = null;
let prevStep  = null;
let runner    = null;   // ScenarioRunner --, non-null only during a scenario

let currentState    = null;
let currentT        = 2;
let autoplayEnabled = true;  // When true, operations play through without pausing on key steps

// ─── DOM refs ─────────────────────────────────────────────────────────────────

const svgEl       = document.getElementById('main-svg');
const sidebarEl   = document.getElementById('sidebar');
const opSelect    = document.getElementById('op-select');
const keyInput    = document.getElementById('key-input');
const tInput      = document.getElementById('t-input');
const tDisplay    = document.getElementById('t-display');
const scenarioSel = document.getElementById('scenario-select');
const btnRun      = document.getElementById('btn-run');
const statusDot   = document.getElementById('status-dot');
const statusLabel = document.getElementById('status-label');

const banner      = document.getElementById('keystep-banner');
const bannerText  = document.getElementById('keystep-banner-text');

const progressTrack = document.getElementById('progress-track');
const progressFill  = document.getElementById('progress-fill');
const progressThumb = document.getElementById('progress-thumb');

const btnToStart    = document.getElementById('btn-to-start');
const btnStepBack   = document.getElementById('btn-step-back');
const btnPlayPause  = document.getElementById('btn-play-pause');
const btnStepFwd    = document.getElementById('btn-step-fwd');
const btnToEnd      = document.getElementById('btn-to-end');
const stepCounter   = document.getElementById('step-counter');
const speedSelect   = document.getElementById('speed-select');
const btnAutoplay   = document.getElementById('btn-autoplay');

const errorToast   = document.getElementById('error-toast');
const validateOverlay  = document.getElementById('validate-overlay');
const validateResults  = document.getElementById('validate-results');
const validateClose    = document.getElementById('validate-close');
const scenarioModal    = document.getElementById('scenario-modal');
const scenarioNameEl   = document.getElementById('scenario-name');
const scenarioDescEl   = document.getElementById('scenario-desc');
const scenarioStart    = document.getElementById('scenario-start');
const scenarioCancel   = document.getElementById('scenario-cancel');

// Stage 9 new elements
const scenarioProgress = document.getElementById('scenario-progress');
const scenarioPipTrack = document.getElementById('scenario-pip-track');
const scenarioOpLabel  = document.getElementById('scenario-op-label');
const announceBanner   = document.getElementById('announce-banner');

// ─── Theme → CSS vars ─────────────────────────────────────────────────────────
//
// Writes every ThemeModule colour and font token to :root as CSS custom
// properties, making ThemeModule.js the single source of truth.
// The :root block in index.html is an initial-paint fallback only.

function applyTheme(theme) {
  const root = document.documentElement.style;
  const pairs = [
    ['--bg-deep',     theme.BG_DEEP],
    ['--bg-surface',  theme.BG_SURFACE],
    ['--bg-surface2', theme.BG_SURFACE2],
    ['--bg-surface3', theme.BG_SURFACE3],
    ['--border',      theme.BORDER],
    ['--border2',     theme.BORDER2],
    ['--text',        theme.TEXT],
    ['--text-muted',  theme.TEXT_MUTED],
    ['--text-dim',    theme.TEXT_DIM],
    ['--gold',        theme.GOLD],
    ['--gold-light',  theme.GOLD_LIGHT],
    ['--gold-bg',     theme.GOLD_BG],
    ['--green',       theme.GREEN],
    ['--green-bg',    theme.GREEN_BG],
    ['--red',         theme.RED],
    ['--red-bg',      theme.RED_BG],
    ['--blue',        theme.BLUE],
    ['--blue-bg',     theme.BLUE_BG],
    ['--purple',      theme.PURPLE],
    ['--purple-bg',   theme.PURPLE_BG],
    ['--orange',      theme.ORANGE],
    ['--orange-bg',   theme.ORANGE_BG],
    ['--ui-font',     theme.UI_FONT],
    ['--code-font',   theme.CODE_FONT],
  ];
  pairs.forEach(([k, v]) => root.setProperty(k, v));

  // --bg-overlay: BG_DEEP at 88% opacity, used by modal backdrops
  const h = theme.BG_DEEP.replace('#', '');
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  root.setProperty('--bg-overlay', `rgba(${r},${g},${b},0.88)`);
}

// ─── Init ─────────────────────────────────────────────────────────────────────

function init() {
  applyTheme(createTheme());

  anim = new AnimationLayer(svgEl, d3);
  narr = new NarrativeLayer(sidebarEl);

  resetTree(currentT);
  updateTDisplay();
  updatePlaybackUI({ status: 'idle', index: 0, total: 0 });

  wireTopbar();
  wirePlayback();
  wireProgressBar();
  wireScenarioModal();
  wireValidateOverlay();
}

function resetTree(t) {
  resetIdCounter();
  currentState = createTree(t);
  currentT     = t;
}

// ─── Tree building ────────────────────────────────────────────────────────────

function buildInitialState(t, keys) {
  resetIdCounter();
  let state = createTree(t);
  for (const k of keys) {
    const steps = insert(state, k);
    state = steps[steps.length - 1].state;
  }
  return state;
}

// ─── Operation runner ─────────────────────────────────────────────────────────

function runOperation(op, key, state, tValue) {
  if (tValue !== currentT) {
    resetTree(tValue);
    state = currentState;
  }

  let steps;
  try {
    if      (op === 'search') steps = search(state, key);
    else if (op === 'insert') { steps = insert(state, key);    currentState = steps[steps.length - 1].state; }
    else if (op === 'delete') { steps = deleteKey(state, key); currentState = steps[steps.length - 1].state; }
    else return null;
  } catch (err) {
    showError(`Error: ${err.message}`);
    return null;
  }

  return startPlayback(steps, op);
}

// ─── Playback ─────────────────────────────────────────────────────────────────

function startPlayback(steps, op) {
  if (ctrl) { ctrl.destroy(); ctrl = null; }
  prevStep = null;

  narr.loadOperation(op);
  hideBanner();
  hideAnnounce();

  const speed = parseFloat(speedSelect.value) || 1;

  ctrl = new PlaybackController(steps, {
    speed,
    pauseOnKeySteps: !autoplayEnabled,  // autoplay = don't pause on key steps
    msPerStep:       800,
  });

  ctrl.on('frame', step => {
    anim.render(step);
    // Inform the controller how long this step's animation takes so it waits
    // until the animation completes before firing the next step.
    if (ctrl) ctrl.setCurrentStepDuration(_planDuration(step, _appTheme));
  });

  ctrl.on('narrative', step => {
    narr.update(step, prevStep);
    prevStep = step;
  });

  ctrl.on('statusChange', s => {
    updatePlaybackUI(s);
    if (s.currentStep?.isKeyStep && s.status === 'paused') {
      showBanner(s.currentStep);
    } else {
      hideBanner();
    }
  });

  buildProgressTicks(steps);
  updateProgressBar(0, steps.length);

  anim.render(steps[0]);
  narr.update(steps[0], null);
  prevStep = steps[0];

  ctrl.play();
  return ctrl;
}

// ─── Progress bar ─────────────────────────────────────────────────────────────

function buildProgressTicks(steps) {
  progressTrack.querySelectorAll('.progress-tick').forEach(el => el.remove());
  steps.forEach((step, i) => {
    if (step.isKeyStep) {
      const pct  = (i / Math.max(steps.length - 1, 1)) * 100;
      const tick = document.createElement('div');
      tick.className   = 'progress-tick';
      tick.style.left  = `${pct}%`;
      progressTrack.appendChild(tick);
    }
  });
}

function updateProgressBar(index, total) {
  const pct = total <= 1 ? 100 : (index / (total - 1)) * 100;
  progressFill.style.width  = `${pct}%`;
  progressThumb.style.left  = `${pct}%`;
  stepCounter.textContent   = total > 0 ? `${index + 1} / ${total}` : '--, / --,';
}

// ─── UI state ─────────────────────────────────────────────────────────────────

function updatePlaybackUI(s) {
  const isIdle = !ctrl || s.status === 'idle';

  statusDot.className     = s.status === 'idle' ? '' : s.status;
  statusLabel.textContent =
    s.status === 'playing'  ? 'Playing' :
    s.status === 'paused'   ? 'Paused'  :
    s.status === 'complete' ? 'Done'    : 'Ready';

  btnPlayPause.textContent = s.status === 'playing' ? '⏸' : '▶';

  btnToStart.disabled   = isIdle;
  btnStepBack.disabled  = isIdle;
  btnStepFwd.disabled   = isIdle || s.status === 'complete';
  btnToEnd.disabled     = isIdle || s.status === 'complete';
  btnPlayPause.disabled = isIdle;

  if (ctrl && s.total > 0) updateProgressBar(s.index, s.total);
}

// ─── Banners ──────────────────────────────────────────────────────────────────

const BANNER_REASONS = {
  overflow:    '⚑ Overflow --, split required',
  underflow:   '⚑ Underflow --, fix required',
  found:       '⚑ Key found',
  'not-found': '⚑ Key not found',
  rotate:      '⚑ Borrow --, key rotation',
  merge:       '⚑ Merge --, pulling separator down',
};

function showBanner(step) {
  const reason = step.meta?.reason;
  bannerText.textContent =
    BANNER_REASONS[reason] ??
    (step.action === 'SPLIT_ROOT'  ? '⚑ Tree height increased' :
     step.action === 'ROOT_SHRINK' ? '⚑ Tree height decreased' :
     '⚑ Key step');
  banner.classList.add('visible');
}
function hideBanner() { banner.classList.remove('visible'); }

let announceTimer = null;
function showAnnounce(text, duration = 2000) {
  announceBanner.textContent = text;
  announceBanner.classList.add('visible');
  clearTimeout(announceTimer);
  announceTimer = setTimeout(() => announceBanner.classList.remove('visible'), duration);
}
function hideAnnounce() {
  clearTimeout(announceTimer);
  announceBanner.classList.remove('visible');
}

// ─── Error toast ──────────────────────────────────────────────────────────────

let toastTimer = null;
function showError(msg) {
  errorToast.textContent = msg;
  errorToast.classList.add('visible');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => errorToast.classList.remove('visible'), 3500);
}

// ─── Validate ─────────────────────────────────────────────────────────────────

function runValidate() {
  if (!currentState) return;
  const errors = validate(currentState);
  const { t, nodes, rootId } = currentState;
  const all = Object.values(nodes);
  const max = 2 * t - 1, min = t - 1;

  const checks = [
    { label: 'All leaves at same depth',         ok: checkLeafDepth(nodes, rootId) },
    { label: `Root has ≥ 1 key`,                 ok: (nodes[rootId]?.keys.length ?? 0) >= 1 || all.length === 1 },
    { label: `Non-root nodes have ≥ t−1=${min} keys`, ok: all.every(n => n.id === rootId || n.keys.length >= min) },
    { label: `All nodes have ≤ 2t−1=${max} keys`,     ok: all.every(n => n.keys.length <= max) },
    { label: 'Internal nodes: children = keys+1',ok: all.every(n => n.isLeaf || n.children.length === n.keys.length + 1) },
    { label: 'All keys sorted within each node', ok: all.every(n => n.keys.every((k,i) => i === 0 || k > n.keys[i-1])) },
    { label: 'All errors from full validation',  ok: errors.length === 0,
      detail: errors.length ? errors.slice(0, 3).join('; ') : null },
  ];

  validateResults.innerHTML = checks.map(c => `
    <div class="validate-row">
      <span>${c.label}${c.detail ? `<br><small style="color:var(--red);font-size:10px">${c.detail}</small>` : ''}</span>
      <span class="${c.ok ? 'validate-ok' : 'validate-err'}">${c.ok ? '✓' : '✗'}</span>
    </div>`).join('');
  validateOverlay.classList.add('visible');
}

function checkLeafDepth(nodes, rootId) {
  const depths = [];
  const walk = (id, d) => { const n = nodes[id]; if (!n) return; if (n.isLeaf) { depths.push(d); return; } for (const c of n.children) walk(c, d+1); };
  walk(rootId, 0);
  return depths.length === 0 || depths.every(d => d === depths[0]);
}

// ─── Scenario: progress indicator ────────────────────────────────────────────

function showScenarioProgress(scenario) {
  // Build pip dots --, one per operation
  const ops = scenario.operations;
  scenarioPipTrack.innerHTML = ops.map((_, i) =>
    `<div class="scenario-pip" id="sp-${i}"></div>`
  ).join('');
  scenarioOpLabel.textContent = `1 / ${ops.length}`;
  scenarioProgress.classList.add('visible');
}

function updateScenarioProgress(opIndex, total) {
  scenarioOpLabel.textContent = `${opIndex + 1} / ${total}`;
  for (let i = 0; i < total; i++) {
    const pip = document.getElementById(`sp-${i}`);
    if (!pip) continue;
    pip.className = 'scenario-pip' +
      (i < opIndex  ? ' done'    :
       i === opIndex ? ' current' : '');
  }
}

function hideScenarioProgress() {
  scenarioProgress.classList.remove('visible');
  scenarioPipTrack.innerHTML = '';
}

// ─── Scenario: load + run ────────────────────────────────────────────────────

function loadScenario(id) {
  const sc = SCENARIO_MAP[id];
  if (!sc) return;

  scenarioNameEl.textContent = sc.name;
  scenarioDescEl.textContent = sc.description;
  scenarioModal.classList.add('visible');

  scenarioStart.onclick = () => {
    scenarioModal.classList.remove('visible');

    // Stop any running scenario
    if (runner) { runner.stop(); runner = null; }

    // Pre-build the initial tree silently
    currentState = buildInitialState(sc.t, sc.initialKeys);
    currentT     = sc.t;
    tInput.value = sc.t;
    updateTDisplay();

    showScenarioProgress(sc);

    runner = new ScenarioRunner(
      sc,
      {
        onOperationStart(op, key, opIndex, total) {
          updateScenarioProgress(opIndex, total);
          opSelect.value = op;
          keyInput.value = key;
        },
        onOperationEnd(_op, _key, _opIndex, _total) {
          // state already updated by runOperation inside startOp
        },
        onAnnounce(message, nextIndex, total) {
          updateScenarioProgress(nextIndex, total);
          showAnnounce(message, (sc.pauseMs ?? 1500) - 200);
        },
        onProgressUpdate(opIndex, total) {
          updateScenarioProgress(opIndex, total);
        },
        onComplete() {
          runner = null;
          hideScenarioProgress();
          hideAnnounce();
          showAnnounce('Scenario complete!', 2500);
          scenarioSel.value = '';
        },
      },
      // startOp: create a playback controller for one operation
      (op, key) => {
        let steps;
        try {
          if      (op === 'search') steps = search(currentState, key);
          else if (op === 'insert') { steps = insert(currentState, key);    currentState = steps[steps.length - 1].state; }
          else if (op === 'delete') { steps = deleteKey(currentState, key); currentState = steps[steps.length - 1].state; }
          else return null;
        } catch (e) {
          showError(`Scenario error: ${e.message}`);
          return null;
        }
        return startPlayback(steps, op);
      }
    );

    runner.start();
  };
}

// ─── User scenario (auto-loaded from parser output) ──────────────────────────
//
// If user-scenario.json exists at the server root, it is injected into
// SCENARIO_MAP and loadScenario() is called exactly as if the user had
// picked it from the dropdown. If the file is absent or malformed, the
// app boots normally with no change in behaviour.

async function checkUserScenario() {
  let sc;
  try {
    const res = await fetch('/user-scenario.json');
    if (!res.ok) return;
    sc = await res.json();
  } catch (_) {
    return; // absent or network error --, boot normally
  }

  sc.id = sc.id ?? 'user-document';
  SCENARIO_MAP[sc.id] = sc;

  // Insert as the first real option (after the placeholder at index 0)
  // so the dropdown shows the scenario name while it is running.
  const opt = document.createElement('option');
  opt.value       = sc.id;
  opt.textContent = sc.name ?? 'Document Scenario';
  scenarioSel.add(opt, 1);
  scenarioSel.value = sc.id;

  loadScenario(sc.id); // reuses all existing modal + runner logic, unchanged
}

// ─── t display ────────────────────────────────────────────────────────────────

function updateTDisplay() {
  const t = parseInt(tInput.value, 10) || 2;
  tDisplay.textContent = `max keys: ${2 * t - 1}`;
}

// ─── Event wiring ─────────────────────────────────────────────────────────────

function wireTopbar() {
  // Populate scenario dropdown from scenarios.js (source of truth)
  SCENARIOS.forEach(sc => {
    const opt = document.createElement('option');
    opt.value       = sc.id;
    opt.textContent = sc.name;
    scenarioSel.appendChild(opt);
  });

  tInput.addEventListener('input', updateTDisplay);

  btnRun.addEventListener('click', () => {
    // Stop any running scenario
    if (runner) { runner.stop(); runner = null; hideScenarioProgress(); }

    const op  = opSelect.value;
    const key = parseInt(keyInput.value, 10);
    const t   = Math.max(2, Math.min(5, parseInt(tInput.value, 10) || 2));

    if (op === 'validate') { runValidate(); return; }

    if (isNaN(key) || key < 1 || key > 9999) {
      showError('Key must be a number between 1 and 9999.');
      return;
    }

    if (t !== currentT) resetTree(t);
    runOperation(op, key, currentState, t);
  });

  keyInput.addEventListener('keydown', e => { if (e.key === 'Enter') btnRun.click(); });
  tInput.addEventListener('keydown',   e => { if (e.key === 'Enter') btnRun.click(); });

  scenarioSel.addEventListener('change', () => {
    const id = scenarioSel.value;
    if (id) loadScenario(id);
  });
}

function wirePlayback() {
  btnPlayPause.addEventListener('click', () => {
    if (!ctrl) return;
    if (ctrl.status === 'playing') { ctrl.pause(); hideBanner(); }
    else ctrl.play();
  });

  btnStepBack.addEventListener('click', () => { if (ctrl) { ctrl.stepBack(); hideBanner(); } });
  btnStepFwd.addEventListener('click',  () => { if (ctrl) ctrl.stepForward(); });
  btnToStart.addEventListener('click',  () => { if (ctrl) { ctrl.seekTo(0); hideBanner(); } });
  btnToEnd.addEventListener('click',    () => { if (ctrl) ctrl.seekTo(ctrl.totalSteps - 1); });
  speedSelect.addEventListener('change', () => { if (ctrl) ctrl.setSpeed(parseFloat(speedSelect.value) || 1); });

  // Autoplay toggle --, when ON, operations play end-to-end without pausing at key steps
  updateAutoplayBtn();
  btnAutoplay.addEventListener('click', () => {
    autoplayEnabled = !autoplayEnabled;
    updateAutoplayBtn();
    // Apply to the currently running controller immediately
    if (ctrl) {
      ctrl._pauseOnKey = !autoplayEnabled;
      // If we just turned autoplay ON and we're paused, resume
      if (autoplayEnabled && ctrl.status === 'paused') ctrl.play();
    }
  });

  document.addEventListener('keydown', e => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
    if (!ctrl) return;
    if (e.key === ' ' || e.key === 'k')           { e.preventDefault(); btnPlayPause.click(); }
    else if (e.key === 'ArrowRight' || e.key === 'l') ctrl.stepForward();
    else if (e.key === 'ArrowLeft'  || e.key === 'j') { ctrl.stepBack(); hideBanner(); }
    else if (e.key === 'Home')  { ctrl.seekTo(0); hideBanner(); }
    else if (e.key === 'End')   ctrl.seekTo(ctrl.totalSteps - 1);
    else if (e.key === 'a')     btnAutoplay.click();
  });
}

function updateAutoplayBtn() {
  if (!btnAutoplay) return;
  if (autoplayEnabled) {
    btnAutoplay.textContent = '⟳ Auto';
    btnAutoplay.title = 'Autoplay ON --, operation plays without pausing (press A to toggle)';
    btnAutoplay.classList.add('active');
  } else {
    btnAutoplay.textContent = '⏸ Step';
    btnAutoplay.title = 'Step mode --, pauses at each key step (press A to toggle)';
    btnAutoplay.classList.remove('active');
  }
}

function wireProgressBar() {
  let dragging = false;
  function seekFrom(e) {
    if (!ctrl) return;
    const rect = progressTrack.getBoundingClientRect();
    const pct  = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    ctrl.seekTo(Math.round(pct * (ctrl.totalSteps - 1)));
    hideBanner();
  }
  progressTrack.addEventListener('mousedown', e => { dragging = true; seekFrom(e); });
  document.addEventListener('mousemove', e => { if (dragging) seekFrom(e); });
  document.addEventListener('mouseup',   () => { dragging = false; });
  progressTrack.addEventListener('click', e => seekFrom(e));
}

function wireScenarioModal() {
  scenarioCancel.addEventListener('click', () => {
    scenarioModal.classList.remove('visible');
    scenarioSel.value = '';
  });
}

function wireValidateOverlay() {
  validateClose.addEventListener('click',     () => validateOverlay.classList.remove('visible'));
  validateOverlay.addEventListener('click',    e  => { if (e.target === validateOverlay) validateOverlay.classList.remove('visible'); });
}

// ─── Animation duration helper ────────────────────────────────────────────────
//
// Computes the total wall-clock duration for a step's animation plan so the
// PlaybackController can wait for animations to finish before firing the next step.

const _appTheme = createTheme();

/**
 * Returns the maximum (delay + duration) across all plan slots for the given step.
 * @param {Step}   step
 * @param {object} theme
 * @returns {number} milliseconds
 */
function _planDuration(step, theme) {
  const plan = choreograph(null, step, theme);
  let max = 0;
  for (const slot of Object.values(plan)) {
    const end = (slot.delay ?? 0) + (slot.duration ?? 0);
    if (end > max) max = end;
  }
  return max;
}

// ─── Boot ─────────────────────────────────────────────────────────────────────

function setSvgSize() {
  const area    = svgEl.parentElement;
  const playbar = document.getElementById('playbar');
  svgEl.setAttribute('width',  area.clientWidth);
  svgEl.setAttribute('height', Math.max(area.clientHeight - playbar.offsetHeight, 100));
}

window.addEventListener('load', () => {
  setSvgSize();
  init();
  checkUserScenario(); // no-op if user-scenario.json is absent
  window.addEventListener('resize', () => { setSvgSize(); if (anim && currentState) anim.fitView(currentState); });
});