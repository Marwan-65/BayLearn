// PlaybackController.js
//
// Controls stepping through a Step[] array. Fires events that the animation
// and narrative layers subscribe to. Has zero knowledge of rendering or D3.
//
// Usage:
//   const ctrl = new PlaybackController(steps, { speed: 1.0, pauseOnKeySteps: true });
//   ctrl.on('frame',        step => animLayer.render(step));
//   ctrl.on('narrative',    step => narrLayer.update(step, prevStep));
//   ctrl.on('statusChange', status => updatePlaybackUI(status));
//   ctrl.play();

class PlaybackController {
  /**
   * @param {Step[]} steps         - Full step array from an operation (search/insert/delete)
   * @param {object} opts
   * @param {number} opts.speed          - Playback multiplier (1.0 = normal, 2.0 = double)
   * @param {boolean} opts.pauseOnKeySteps - Auto-pause whenever step.isKeyStep is true
   * @param {number} opts.msPerStep      - Base milliseconds between steps at speed=1.0
   */
  constructor(steps, opts = {}) {
    if (!Array.isArray(steps) || steps.length === 0) {
      throw new Error('PlaybackController requires a non-empty steps array');
    }

    this._steps   = steps;
    this._index   = 0;
    this._speed   = opts.speed         ?? 1.0;
    this._pauseOnKey = opts.pauseOnKeySteps ?? true;
    this._msPerStep  = opts.msPerStep   ?? 800;

    this._status  = 'idle';    // 'idle' | 'playing' | 'paused' | 'complete'
    this._timerId = null;
    this._listeners = {};      // eventName → [callback]
    this._destroyed = false;

    // Fire the initial frame so the view is populated before the user hits play
    this._emit('frame',     this._steps[0]);
    this._emit('narrative', this._steps[0]);
  }

  // ── Public API ──────────────────────────────────────────────────────────────

  /** Register an event listener. Returns `this` for chaining. */
  on(event, fn) {
    if (!this._listeners[event]) this._listeners[event] = [];
    this._listeners[event].push(fn);
    return this;
  }

  /** Remove a previously registered listener. */
  off(event, fn) {
    if (!this._listeners[event]) return this;
    this._listeners[event] = this._listeners[event].filter(cb => cb !== fn);
    return this;
  }

  /** Start or resume auto-play. */
  play() {
    if (this._destroyed) return;
    if (this._status === 'complete') return;

    this._setStatus('playing');
    this._scheduleNext();
  }

  /** Pause auto-play. The current step stays rendered. */
  pause() {
    if (this._destroyed) return;
    this._clearTimer();
    if (this._status !== 'complete') {
      this._setStatus('paused');
    }
  }

  /** Advance exactly one step. Pauses auto-play if it was running. */
  stepForward() {
    if (this._destroyed) return;
    this._clearTimer();
    this._setStatus('paused');
    this._advance();
  }

  /** Go back exactly one step. Pauses auto-play if it was running. */
  stepBack() {
    if (this._destroyed) return;
    this._clearTimer();
    if (this._index > 0) {
      this._index--;
      this._setStatus('paused');
      this._fireStep();
    }
  }

  /** Jump directly to a specific step index. */
  seekTo(index) {
    if (this._destroyed) return;
    const clamped = Math.max(0, Math.min(index, this._steps.length - 1));
    this._clearTimer();
    this._index = clamped;
    this._setStatus(clamped === this._steps.length - 1 ? 'complete' : 'paused');
    this._fireStep();
  }

  /** Set playback speed multiplier. Applies to the next scheduled step. */
  setSpeed(speed) {
    if (typeof speed !== 'number' || speed <= 0) {
      throw new Error(`setSpeed: speed must be a positive number, got ${speed}`);
    }
    this._speed = speed;
  }

  /**
   * Notify the controller how long the CURRENT step's animation takes (ms).
   * _scheduleNext will use max(msPerStep, animationMs) as the inter-step delay.
   * Call this from the 'frame' listener after rendering.
   */
  setCurrentStepDuration(animationMs) {
    this._currentAnimMs = typeof animationMs === 'number' ? animationMs : 0;
  }

  /** Read-only: current status. */
  get status() { return this._status; }

  /** Read-only: current step index (0-based). */
  get currentIndex() { return this._index; }

  /** Read-only: total number of steps. */
  get totalSteps() { return this._steps.length; }

  /** Read-only: the step object at the current index. */
  get currentStep() { return this._steps[this._index]; }

  /**
   * Tear down completely. Clears the timer, removes all listeners.
   * Must be called before replacing the controller with a new one.
   */
  destroy() {
    this._clearTimer();
    this._listeners = {};
    this._destroyed = true;
  }

  // ── Internal ────────────────────────────────────────────────────────────────

  _setStatus(newStatus) {
    if (this._status === newStatus) return;
    this._status = newStatus;
    this._emit('statusChange', {
      status:      newStatus,
      index:       this._index,
      total:       this._steps.length,
      currentStep: this._steps[this._index],
    });
  }

  _advance() {
    if (this._index >= this._steps.length - 1) {
      this._setStatus('complete');
      return;
    }

    this._index++;
    this._fireStep();

    // If we just landed on the last step, mark complete
    if (this._index === this._steps.length - 1) {
      this._setStatus('complete');
      return;
    }

    // Auto-pause on key steps if the option is set and we're in auto-play
    if (this._pauseOnKey && this._steps[this._index].isKeyStep && this._status === 'playing') {
      this._clearTimer();
      this._setStatus('paused');
    }
  }

  _fireStep() {
    const step = this._steps[this._index];
    this._emit('frame',     step);
    this._emit('narrative', step);
  }

  _scheduleNext() {
    if (this._status !== 'playing') return;
    if (this._index >= this._steps.length - 1) {
      this._setStatus('complete');
      return;
    }

    // Use the longer of msPerStep or the current step's animation duration,
    // plus a small 100ms buffer so the animation can settle before the next step.
    const animMs = this._currentAnimMs ?? 0;
    const delay  = Math.max(this._msPerStep, animMs + 100) / this._speed;
    this._currentAnimMs = 0; // reset for next step

    this._timerId = setTimeout(() => {
      if (this._destroyed || this._status !== 'playing') return;
      this._advance();
      if (this._status === 'playing') this._scheduleNext();
    }, delay);
  }

  _clearTimer() {
    if (this._timerId !== null) {
      clearTimeout(this._timerId);
      this._timerId = null;
    }
  }

  _emit(event, data) {
    const cbs = this._listeners[event];
    if (!cbs) return;
    for (const cb of cbs) {
      try {
        cb(data);
      } catch (err) {
        // Listener errors should never crash the controller
        console.error(`PlaybackController: error in '${event}' listener:`, err);
      }
    }
  }
}

module.exports = { PlaybackController };
