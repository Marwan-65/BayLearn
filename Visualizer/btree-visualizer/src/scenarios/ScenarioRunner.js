// src/scenarios/ScenarioRunner.js
//
// Manages the sequential playback of a multi-operation scenario.
// Emits events so app.js can wire it to the existing PlaybackController
// pipeline without knowing about internal sequencing.
//
// Events:
//   onOperationStart(op, key, opIndex, total)
//   onOperationEnd(op, key, opIndex, total)
//   onAnnounce(message, nextIndex, total)
//   onProgressUpdate(opIndex, total)
//   onComplete()

class ScenarioRunner {
  /**
   * @param {object}   scenario   - one entry from SCENARIOS
   * @param {object}   callbacks  - event handlers (all optional)
   * @param {function} startOp    - (op, key) → PlaybackController|null
   */
  constructor(scenario, callbacks, startOp) {
    this._scenario   = scenario;
    this._cbs        = callbacks ?? {};
    this._startOp    = startOp;
    this._opIndex    = 0;
    this._stopped    = false;
    this._started    = false;
    this._pauseTimer = null;
  }

  // ── Public API ──────────────────────────────────────────────────────────────

  start() {
    this._opIndex = 0;
    this._stopped = false;
    this._started = true;
    this._runNext();
  }

  stop() {
    this._stopped = true;
    this._started = false;
    if (this._pauseTimer !== null) {
      clearTimeout(this._pauseTimer);
      this._pauseTimer = null;
    }
  }

  get totalOperations() { return this._scenario.operations.length; }
  get currentIndex()    { return this._opIndex; }
  get isRunning()       { return this._started && !this._stopped && this._opIndex < this.totalOperations; }

  // ── Internal ────────────────────────────────────────────────────────────────

  _runNext() {
    if (this._stopped) return;

    const ops   = this._scenario.operations;
    const total = ops.length;

    if (this._opIndex >= total) {
      this._started = false;
      this._cbs.onComplete?.();
      return;
    }

    const { op, key } = ops[this._opIndex];
    const opIndex     = this._opIndex;

    this._cbs.onProgressUpdate?.(opIndex, total);
    this._cbs.onOperationStart?.(op, key, opIndex, total);

    const ctrl = this._startOp(op, key);
    if (!ctrl) {
      this.stop();
      return;
    }

    const onStatus = (s) => {
      if (s.status !== 'complete') return;
      ctrl.off('statusChange', onStatus);

      this._cbs.onOperationEnd?.(op, key, opIndex, total);
      this._opIndex++;

      if (this._stopped) return;

      const isDone = this._opIndex >= total;
      if (isDone) {
        this._started = false;
        this._cbs.onComplete?.();
        return;
      }

      // Announce next op
      const next = ops[this._opIndex];
      this._cbs.onAnnounce?.(
        `Next: ${this._formatOp(next.op)}(${next.key})`,
        this._opIndex,
        total
      );
      this._cbs.onProgressUpdate?.(this._opIndex, total);

      const delay = this._scenario.pauseMs ?? 1500;
      if (delay === 0) {
        // Run synchronously so tests don't need fake timers
        this._runNext();
      } else {
        this._pauseTimer = setTimeout(() => {
          this._pauseTimer = null;
          if (!this._stopped) this._runNext();
        }, delay);
      }
    };

    ctrl.on('statusChange', onStatus);
  }

  _formatOp(op) {
    const labels = { insert: 'Insert', delete: 'Delete', search: 'Search' };
    return labels[op] ?? op;
  }
}

module.exports = { ScenarioRunner };