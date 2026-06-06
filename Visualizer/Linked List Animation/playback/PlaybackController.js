
export const STATUS = Object.freeze({
  IDLE:    'idle',     // loaded, not yet started
  PLAYING: 'playing',  // auto-advancing
  PAUSED:  'paused',   // manually or auto-paused
  DONE:    'done',     // reached the last step
});

const BASE_INTERVAL_MS = 900;

const MIN_INTERVAL_MS = 80;


export class PlaybackController {

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

    this._listeners = {
      frame:        new Set(),
      narrative:    new Set(),
      statusChange: new Set(),
      complete:     new Set(),
    };
  }


  get currentIndex()  { return this._index; }
  get totalSteps()    { return this._steps.length; }
  get currentStep()   { return this._steps[this._index]; }
  get status()        { return this._status; }
  get speed()         { return this._speed; }
  get isPlaying()     { return this._status === STATUS.PLAYING; }
  get isAtStart()     { return this._index === 0; }
  get isAtEnd()       { return this._index === this._steps.length - 1; }

  get progress() {
    if (this._steps.length <= 1) return 1;
    return this._index / (this._steps.length - 1);
  }


  on(event, fn) {
    if (!this._listeners[event]) {
      throw new Error(`Unknown event "${event}". Valid: ${Object.keys(this._listeners).join(', ')}`);
    }
    this._listeners[event].add(fn);
    return () => this._listeners[event].delete(fn);
  }

  off(event, fn) {
    this._listeners[event]?.delete(fn);
  }


  play() {
    if (this._status === STATUS.PLAYING) return;

    if (this.isAtEnd) {
      this._setIndex(0);
    }

    this._setStatus(STATUS.PLAYING);
    this._scheduleNext();
  }

  pause() {
    if (this._status !== STATUS.PLAYING) return;
    this._clearTimer();
    this._setStatus(STATUS.PAUSED);
  }

  togglePlay() {
    this.isPlaying ? this.pause() : this.play();
  }

  stepForward() {
    if (this.isAtEnd) return;
    this._clearTimer();
    if (this._status === STATUS.PLAYING) this._setStatus(STATUS.PAUSED);
    this._setIndex(this._index + 1);
  }


  stepBack() {
    if (this.isAtStart) return;
    this._clearTimer();
    if (this._status === STATUS.PLAYING) this._setStatus(STATUS.PAUSED);
    this._setIndex(this._index - 1);
  }


  jumpTo(index) {
    const clamped = Math.max(0, Math.min(this._steps.length - 1, index));
    this._clearTimer();
    if (this._status === STATUS.PLAYING) this._setStatus(STATUS.PAUSED);
    this._setIndex(clamped);
  }

  rewind() {
    this.jumpTo(0);
    this._setStatus(STATUS.IDLE);
  }

  jumpToEnd() {
    this.jumpTo(this._steps.length - 1);
  }

  nextKeyStep() {
    const nextIdx = this._steps.findIndex(
      (s, i) => i > this._index && s.isKeyStep
    );
    if (nextIdx !== -1) this.jumpTo(nextIdx);
    else this.jumpToEnd();
  }


  prevKeyStep() {
    let i = this._index - 1;
    while (i >= 0) {
      if (this._steps[i].isKeyStep) { this.jumpTo(i); return; }
      i--;
    }
    this.rewind();
  }


  setSpeed(speed) {
    this._speed = Math.max(0.1, speed);
    // If currently playing, restart the timer with the new interval
    if (this.isPlaying) {
      this._clearTimer();
      this._scheduleNext();
    }
  }


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


  destroy() {
    this._clearTimer();
    Object.values(this._listeners).forEach(s => s.clear());
  }


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


  _advance() {
    if (this.isAtEnd) {
      this._setStatus(STATUS.DONE);
      this._emit('complete', undefined);
      return;
    }

    const nextIndex = this._index + 1;
    this._setIndex(nextIndex);

    const step = this._steps[nextIndex];

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