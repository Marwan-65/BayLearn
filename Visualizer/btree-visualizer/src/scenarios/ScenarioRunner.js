
// da el file el byhandle el scenario generation w el sequencing, byet2aked en el operations elly mawgooda fe el scenario betet3amal wa7da wa7da b correct timing w en el events elly byetfire fe el right moments w consistent ma3 el operations sequence. w kaman en el callbacks elly byetfire ma3a kol event byet3araf beha sah w consistent ma3a el arguments elly byetfire ma3aha.

class ScenarioRunner {
  // el input homa scenario object (one entry from SCENARIOS), callbacks object (event handlers, all optional), w startOp function (byet3ayen beha el operation elly hatet3amal, byetreceiv op w key w byerga3 PlaybackController or null)
  constructor(scenario, callbacks, startOp) {
    this._scenario   = scenario;
    this._cbs  = callbacks ?? {};
    this._startOp = startOp;
    this._opIndex    = 0;
    this._stopped = false;
    this._started = false;
    this._pauseTimer = null;
  }


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
// w dol el getters elly byet2aked en el state reporting byet3amal sah w consistent, we check en totalOperations byet3araf beha sah w consistent ma3a scenario.operations.length, w en currentIndex byet3araf beha sah w consistent ma3a the current operation index, w en isRunning byet3araf beha sah w consistent ma3a the started/stopped state and the current index.
  get totalOperations() { return this._scenario.operations.length; }
  get currentIndex()  { return this._opIndex; }
  get isRunning()  { return this._started && !this._stopped && this._opIndex < this.totalOperations; }

// da el method elly betrun el scenario, byet2aked en el sequencing sah w consistent ma3a the operations array in the scenario, w en el callbacks byetfire ma3a kol event b sah w consistent ma3a the current operation w index. w kaman en el timing of the operations is consistent ma3 the pauseMs property in the scenario (e.g. if pauseMs is 0, all operations should run synchronously without delay).
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

      // announce el next operation, w enna el progress update byetfire ma3a kol operation end w consistent ma3a the new index. w kaman en el timing of the next operation is consistent ma3 the pauseMs property in the scenario (e.g. if pauseMs is 0, the next operation should start immediately without delay).
      const next = ops[this._opIndex];
      this._cbs.onAnnounce?.(
        `Next: ${this._formatOp(next.op)}(${next.key})`,
        this._opIndex,
        total
      );
      this._cbs.onProgressUpdate?.(this._opIndex, total);

      const delay = this._scenario.pauseMs ?? 1500;
      if (delay === 0) {
        //  lw pauseMs howa 0, el next operation byetrun immediately without delay, w enna el callbacks byetfire ma3a kol event b sah w consistent ma3a the new operation w index.
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