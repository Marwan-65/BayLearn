/**
 * PLAYBACK CONTROLLER
 *
 * The single source of truth for "where are we in the animation right now."
 *
 * Responsibilities:
 *   - Owns the step array and the current index
 *   - Exposes play / pause / stepForward / stepBack / jumpTo / setSpeed
 *   - On every index change, fires two independent events:
 *       "frame"     → consumed by the Animation Layer (SVG/D3)
 *       "narrative" → consumed by the Narrative Layer (text, code, variables)
 *   - Has no knowledge of D3, SVG, DOM, or React --, it is pure JS
 *
 * ─── Event contract ───────────────────────────────────────────────────────────
 *
 *   "frame" payload     → the full Step object (animation layer reads highlights + state)
 *   "narrative" payload → the full Step object (narrative layer reads explanation + variables + pseudocodeLine)
 *   "statusChange"      → { status, currentIndex, totalSteps, progress }
 *   "complete"          → fires once when the last step is reached during play()
 *
 * Both layers receive the SAME step object --, they just read different fields from it.
 *
 * ─── Usage ────────────────────────────────────────────────────────────────────
 *
 *   import { PlaybackController } from './playback/PlaybackController.js';
 *   import { fromArray, insertAtHead } from './index.js';
 *
 *   const steps = insertAtHead(fromArray([2, 3, 4]), 1);
 *   const ctrl  = new PlaybackController(steps, { speed: 1.0 });
 *
 *   ctrl.on('frame',     step  => animationLayer.render(step));
 *   ctrl.on('narrative', step  => narrativeLayer.update(step));
 *   ctrl.on('complete',  ()    => console.log('done'));
 *
 *   ctrl.play();
 */

// ─── Constants ────────────────────────────────────────────────────────────────

export const STATUS = Object.freeze({
  IDLE:    'idle',     // loaded, not yet started
  PLAYING: 'playing',  // auto-advancing
  PAUSED:  'paused',   // manually or auto-paused
  DONE:    'done',     // reached the last step
});

/** Milliseconds per step at speed = 1.0 */
const BASE_INTERVAL_MS = 900;

/** Minimum interval regardless of speed setting */
const MIN_INTERVAL_MS = 80;

// ─── PlaybackController ───────────────────────────────────────────────────────

export class PlaybackController {
  /**
   * @param {Step[]} steps   - Output from any operation function
   * @param {object} options
   * @param {number} [options.speed=1.0]         - Playback multiplier (0.25 – 4.0)
   * @param {boolean} [options.pauseOnKeySteps=true] - Auto-pause when step.isKeyStep is true
   */
  constructor(steps, options = {}) {
    if (!Array.isArray(steps) || steps.length === 0) {
      throw new Error('PlaybackController requires a non-empty steps array.');
    }

    this._steps  = steps;
    this._index  = 0;
    this._status = STATUS.IDLE;
    this._timer  = null;

    this._speed          = options.speed          ?? 1.0;
    this._pauseOnKeySteps = options.pauseOnKeySteps ?? true;

    // Event listener registry  { eventName: Set<fn> }
    this._listeners = {
      frame:        new Set(),
      narrative:    new Set(),
      statusChange: new Set(),
      complete:     new Set(),
    };
  }

  // ─── Public getters ─────────────────────────────────────────────────────────

  get currentIndex()  { return this._index; }
  get totalSteps()    { return this._steps.length; }
  get currentStep()   { return this._steps[this._index]; }
  get status()        { return this._status; }
  get speed()         { return this._speed; }
  get isPlaying()     { return this._status === STATUS.PLAYING; }
  get isAtStart()     { return this._index === 0; }
  get isAtEnd()       { return this._index === this._steps.length - 1; }

  /** 0.0 – 1.0 progress through the step sequence */
  get progress() {
    if (this._steps.length <= 1) return 1;
    return this._index / (this._steps.length - 1);
  }

  // ─── Event system ───────────────────────────────────────────────────────────

  /**
   * Register a listener for an event.
   * Returns an unsubscribe function for easy cleanup.
   *
   * @param {'frame'|'narrative'|'statusChange'|'complete'} event
   * @param {Function} fn
   * @returns {Function} unsubscribe
   */
  on(event, fn) {
    if (!this._listeners[event]) {
      throw new Error(`Unknown event "${event}". Valid: ${Object.keys(this._listeners).join(', ')}`);
    }
    this._listeners[event].add(fn);
    return () => this._listeners[event].delete(fn);
  }

  /** Remove a specific listener */
  off(event, fn) {
    this._listeners[event]?.delete(fn);
  }

  // ─── Playback controls ──────────────────────────────────────────────────────

  /**
   * Start auto-playing from the current position.
   * If already at the end, rewinds to the start first.
   */
  play() {
    if (this._status === STATUS.PLAYING) return;

    if (this.isAtEnd) {
      this._setIndex(0);
    }

    this._setStatus(STATUS.PLAYING);
    this._scheduleNext();
  }

  /** Pause auto-play. Has no effect if not currently playing. */
  pause() {
    if (this._status !== STATUS.PLAYING) return;
    this._clearTimer();
    this._setStatus(STATUS.PAUSED);
  }

  /** Toggle between play and pause. */
  togglePlay() {
    this.isPlaying ? this.pause() : this.play();
  }

  /**
   * Advance one step forward.
   * Pauses if currently playing.
   * No-op if already at the end.
   */
  stepForward() {
    if (this.isAtEnd) return;
    this._clearTimer();
    if (this._status === STATUS.PLAYING) this._setStatus(STATUS.PAUSED);
    this._setIndex(this._index + 1);
  }

  /**
   * Go back one step.
   * Pauses if currently playing.
   * No-op if already at the start.
   */
  stepBack() {
    if (this.isAtStart) return;
    this._clearTimer();
    if (this._status === STATUS.PLAYING) this._setStatus(STATUS.PAUSED);
    this._setIndex(this._index - 1);
  }

  /**
   * Jump to a specific step index.
   * Pauses if currently playing.
   *
   * @param {number} index
   */
  jumpTo(index) {
    const clamped = Math.max(0, Math.min(this._steps.length - 1, index));
    this._clearTimer();
    if (this._status === STATUS.PLAYING) this._setStatus(STATUS.PAUSED);
    this._setIndex(clamped);
  }

  /** Jump to the first step. */
  rewind() {
    this.jumpTo(0);
    this._setStatus(STATUS.IDLE);
  }

  /** Jump to the last step. */
  jumpToEnd() {
    this.jumpTo(this._steps.length - 1);
  }

  /**
   * Jump to the next step whose isKeyStep === true.
   * Useful for "fast-forward through setup steps" mode.
   */
  nextKeyStep() {
    const nextIdx = this._steps.findIndex(
      (s, i) => i > this._index && s.isKeyStep
    );
    if (nextIdx !== -1) this.jumpTo(nextIdx);
    else this.jumpToEnd();
  }

  /**
   * Jump back to the previous isKeyStep.
   */
  prevKeyStep() {
    let i = this._index - 1;
    while (i >= 0) {
      if (this._steps[i].isKeyStep) { this.jumpTo(i); return; }
      i--;
    }
    this.rewind();
  }

  /**
   * Set playback speed.
   * @param {number} speed  0.25 = quarter speed, 2.0 = double speed, etc.
   */
  setSpeed(speed) {
    this._speed = Math.max(0.1, speed);
    // If currently playing, restart the timer with the new interval
    if (this.isPlaying) {
      this._clearTimer();
      this._scheduleNext();
    }
  }

  /**
   * Load a completely new step sequence (e.g. after the user triggers a
   * different operation) and reset to the start.
   *
   * @param {Step[]} steps
   */
  loadSteps(steps) {
    if (!Array.isArray(steps) || steps.length === 0) {
      throw new Error('loadSteps requires a non-empty steps array.');
    }
    this._clearTimer();
    this._steps  = steps;
    this._index  = 0;
    this._status = STATUS.IDLE;
    this._emit('statusChange', this._statusPayload());
    this._dispatchCurrentStep();   // immediately show the first frame
  }

  /**
   * Remove all listeners and stop any running timer.
   * Call this when the component/view using the controller is destroyed.
   */
  destroy() {
    this._clearTimer();
    Object.values(this._listeners).forEach(s => s.clear());
  }

  // ─── Private: timer management ──────────────────────────────────────────────

  _intervalMs() {
    return Math.max(MIN_INTERVAL_MS, BASE_INTERVAL_MS / this._speed);
  }

  _scheduleNext() {
    this._timer = setTimeout(() => {
      this._advance();
    }, this._intervalMs());
  }

  _clearTimer() {
    if (this._timer !== null) {
      clearTimeout(this._timer);
      this._timer = null;
    }
  }

  /**
   * Called on each timer tick during play().
   * Advances the index by one, handles key-step pausing and end-of-sequence.
   */
  _advance() {
    if (this.isAtEnd) {
      this._setStatus(STATUS.DONE);
      this._emit('complete', undefined);
      return;
    }

    const nextIndex = this._index + 1;
    this._setIndex(nextIndex);

    const step = this._steps[nextIndex];

    // Auto-pause on key steps if that option is enabled
    if (this._pauseOnKeySteps && step.isKeyStep) {
      this._setStatus(STATUS.PAUSED);
      return;
    }

    if (this.isAtEnd) {
      this._setStatus(STATUS.DONE);
      this._emit('complete', undefined);
      return;
    }

    this._scheduleNext();
  }

  // ─── Private: state mutation helpers ────────────────────────────────────────

  _setIndex(index) {
    this._index = index;
    this._dispatchCurrentStep();
    this._emit('statusChange', this._statusPayload());
  }

  _setStatus(status) {
    this._status = status;
    this._emit('statusChange', this._statusPayload());
  }

  _dispatchCurrentStep() {
    const step = this._steps[this._index];
    this._emit('frame',     step);   // → Animation Layer
    this._emit('narrative', step);   // → Narrative Layer
  }

  _statusPayload() {
    return {
      status:       this._status,
      currentIndex: this._index,
      totalSteps:   this._steps.length,
      progress:     this.progress,
    };
  }

  _emit(event, payload) {
    this._listeners[event]?.forEach(fn => {
      try { fn(payload); }
      catch (err) {
        console.error(`[PlaybackController] Error in "${event}" listener:`, err);
      }
    });
  }
}