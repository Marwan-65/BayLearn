import { fromArray } from '../index.js';
import { PlaybackController } from '../playback/PlaybackController.js';
import { AnimationLayer } from '../animation/Animationlayer.js';
import { NarrativeLayer } from '../narrative/NarrativeLayer.js';
import { buildSteps } from './operationDispatcher.js';

/**
 * Long-lived app orchestrator.
 * Owns wiring between playback controller, animation layer, and narrative layer.
 */
export class LinkedListApp {
  /**
   * @param {object} options
   * @param {SVGElement} options.svgEl
   * @param {HTMLElement} options.sidebarEl
   * @param {object} options.d3
   * @param {number} [options.speed=1]
   * @param {boolean} [options.pauseOnKeySteps=true]
   * @param {(statusPayload: object) => void} [options.onStatusChange]
   * @param {() => void} [options.onComplete]
   */
  constructor({
    svgEl,
    sidebarEl,
    d3,
    speed = 1,
    pauseOnKeySteps = true,
    onStatusChange,
    onComplete,
  }) {
    if (!svgEl) throw new Error('LinkedListApp requires svgEl.');
    if (!sidebarEl) throw new Error('LinkedListApp requires sidebarEl.');
    if (!d3) throw new Error('LinkedListApp requires a d3 instance.');

    this._anim = new AnimationLayer(svgEl, d3);
    this._narr = new NarrativeLayer(sidebarEl);

    this._ctrl = null;
    this._defaultSpeed = speed;
    this._pauseOnKeySteps = pauseOnKeySteps;

    this._onStatusChange = onStatusChange;
    this._onComplete = onComplete;
  }

  /**
   * Runs an operation using an existing ListState.
   *
   * @param {string} operationKey
   * @param {object} list
   * @param  {...any} params
   * @returns {Array<object>} generated steps
   */
  runOperation(operationKey, list, ...params) {
    const steps = buildSteps(operationKey, list, params);
    if (!Array.isArray(steps) || steps.length === 0) {
      throw new Error(`No steps generated for operation "${operationKey}".`);
    }

    // Must load operation metadata before first narrative update.
    this._narr.loadOperation(operationKey);

    if (this._ctrl) this._ctrl.destroy();
    this._ctrl = new PlaybackController(steps, {
      speed: this._defaultSpeed,
      pauseOnKeySteps: this._pauseOnKeySteps,
    });

    // Keep prevStep in app wiring closure, not inside any layer.
    let prevStep = null;

    this._ctrl.on('frame', (step) => {
      this._anim.render(step);
    });

    this._ctrl.on('narrative', (step) => {
      this._narr.update(step, prevStep);
      prevStep = step;
    });

    this._ctrl.on('statusChange', (payload) => {
      this._onStatusChange?.(payload);
    });

    this._ctrl.on('complete', () => {
      this._onComplete?.();
    });

    // Render first frame immediately so the UI is never blank before play.
    this._anim.render(steps[0]);
    this._narr.update(steps[0], null);
    this._anim.resetView(steps[0].state);

    return steps;
  }

  /**
   * Convenience helper: build ListState from raw values and run operation.
   *
   * @param {string} operationKey
   * @param {Array<*>} values
   * @param  {...any} params
   * @returns {Array<object>} generated steps
   */
  runFromValues(operationKey, values, ...params) {
    const list = fromArray(values);
    return this.runOperation(operationKey, list, ...params);
  }

  get controller() {
    return this._ctrl;
  }

  setSpeed(speed) {
    this._defaultSpeed = Math.max(0.1, Number(speed) || 1);
    if (this._ctrl) this._ctrl.setSpeed(this._defaultSpeed);
  }

  destroy() {
    this._ctrl?.destroy();
    this._narr?.destroy?.();
    this._anim?.destroy?.();
    this._ctrl = null;
  }
}

/**
 * Minimal bootstrap for the required HTML contract:
 *
 * <aside id="sidebar">...</aside>
 * <svg id="viz-svg"></svg>
 */
export function createAppFromDom({
  d3,
  svgSelector = '#viz-svg',
  sidebarSelector = '#sidebar',
  speed = 1,
  pauseOnKeySteps = true,
  onStatusChange,
  onComplete,
} = {}) {
  const svgEl = document.querySelector(svgSelector);
  const sidebarEl = document.querySelector(sidebarSelector);

  return new LinkedListApp({
    svgEl,
    sidebarEl,
    d3,
    speed,
    pauseOnKeySteps,
    onStatusChange,
    onComplete,
  });
}
