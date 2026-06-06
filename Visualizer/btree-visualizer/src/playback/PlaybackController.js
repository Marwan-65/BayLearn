
//da el playback controller elly byet2aked en el sequencing sah w consistent ma3a the steps array eli byet2adem laha, w enna el events eli byetfire ma3a kol step b sah w consistent ma3a the step object w index. w kaman en el timing of the auto-play (play/pause) consistent ma3 the speed property w the pauseOnKeySteps option (e.g. if pauseOnKeySteps is true, auto-play should pause immediately upon landing on a key step). w akid en el public API methods (play, pause, stepForward, stepBack, seekTo, setSpeed) byet2aked enhom byet3amaloo el expected behavior consistently. w akid kaman en el destroy method byet2aked enha btetnada sah w consistent ma3a the destroyed state (e.g. after destroy is called, no further events should fire and all methods should be no-ops).
class PlaybackController {
  // el function bta5od el steps array w options object (feha speed multiplier, pauseOnKeySteps boolean, w msPerStep eli howa el base delay between steps at normal speed). w el constructor byet2aked en el steps array non-empty w sah, w enna el options byet3amal defaulting sah (e.g. speed default to 1.0, pauseOnKeySteps default to true, msPerStep default to 800ms). w kaman en el initial frame byetfire ma3a the first step immediately upon construction, w consistent ma3 the currentIndex being 0 and the status being 'idle'.
  constructor(steps, opts = {}) {
    if (!Array.isArray(steps) || steps.length === 0) {
      throw new Error('PlaybackController requires a non-empty steps array');
    }

    this._steps   = steps;
    this._index   = 0;
    this._speed   = opts.speed         ?? 1.0;
    this._pauseOnKey = opts.pauseOnKeySteps ?? true;
    this._msPerStep  = opts.msPerStep   ?? 800;

    this._status  = 'idle';    //el options homa idle, playing, paused, complete
    this._timerId = null;
    this._listeners = {};      // eventName -> [callback]
    this._destroyed = false;

    // bt fire el initial frame immediately upon construction, w consistent ma3 the currentIndex being 0 and the status being 'idle'.
    this._emit('frame',     this._steps[0]);
    this._emit('narrative', this._steps[0]);
  }


  // el public API methods (play, pause, stepForward, stepBack, seekTo, setSpeed) byet2aked enhom byet3amaloo el expected behavior consistently. w akid kaman en el destroy method byet2aked enha btetnada sah w consistent ma3a the destroyed state (e.g. after destroy is called, no further events should fire and all methods should be no-ops).
  on(event, fn) {
    if (!this._listeners[event]) this._listeners[event] = [];
    this._listeners[event].push(fn);
    return this;
  }

  //off method byet2aked enha btetnada sah w consistent ma3a the listeners state (e.g. if a listener is removed, it should no longer be called on events).
  off(event, fn) {
    if (!this._listeners[event]) return this;
    this._listeners[event] = this._listeners[event].filter(cb => cb !== fn);
    return this;
  }

  // play method byet2aked enha btetnada sah w consistent ma3a the status (e.g. if play is called while already playing, it should have no effect; if called while paused, it should resume auto-play from the current step).
  play() {
    if (this._destroyed) return;
    if (this._status === 'complete') return;

    this._setStatus('playing');
    this._scheduleNext();
  }

  // pause method byet2aked enha btetnada sah w consistent ma3a the status (e.g. if pause is called while already paused or idle, it should have no effect; if called while playing, it should pause auto-play and keep the current step index unchanged).
  pause() {
    if (this._destroyed) return;
    this._clearTimer();
    if (this._status !== 'complete') {
      this._setStatus('paused');
    }
  }

  // stepForward method byet2aked enha btetnada sah w consistent ma3a the index and status (e.g. if stepForward is called while at the last step, it should have no effect; if called while paused or idle, it should advance one step and stay paused; if called while playing, it should advance one step and then pause).
  stepForward() {
    if (this._destroyed) return;
    this._clearTimer();
    this._setStatus('paused');
    this._advance();
  }

  // stepBack method byet2aked enha btetnada sah w consistent ma3a the index and status (e.g. if stepBack is called while at the first step, it should have no effect; otherwise, it should move back one step and pause).
  stepBack() {
    if (this._destroyed) return;
    this._clearTimer();
    if (this._index > 0) {
      this._index--;
      this._setStatus('paused');
      this._fireStep();
    }
  }

  // 
  seekTo(index) {
    if (this._destroyed) return;
    const clamped = Math.max(0, Math.min(index, this._steps.length - 1));
    this._clearTimer();
    this._index = clamped;
    this._setStatus(clamped === this._steps.length - 1 ? 'complete' : 'paused');
    this._fireStep();
  }

  // hena bye3mel set ll speed multiplier, w enna el timing of the auto-play is consistent ma3 the new speed (e.g. if speed is increased, the delay between steps should decrease proportionally). w akid enna el speed must be a positive number, w enna calling setSpeed with an invalid value should throw an error and not change the current speed.
  setSpeed(speed) {
    if (typeof speed !== 'number' || speed <= 0) {
      throw new Error(`setSpeed: speed must be a positive number, got ${speed}`);
    }
    this._speed = speed;
  }


  // el setCurrentStepDuration method byet2aked enha btetnada sah w consistent ma3a the current step's animation duration (e.g. if setCurrentStepDuration is called with a certain duration, the next auto-play delay should be at least that duration, even if msPerStep is shorter). w akid enna calling setCurrentStepDuration with an invalid value (e.g. negative number, non-number) should throw an error and not change the current animation duration.
  setCurrentStepDuration(animationMs) {
    this._currentAnimMs = typeof animationMs === 'number' ? animationMs : 0;
  }

  get status() { return this._status; }

  get currentIndex() { return this._index; }

  get totalSteps() { return this._steps.length; }

  get currentStep() { return this._steps[this._index]; }


  // hena finally bte3mel  el destroy
  destroy() {
    this._clearTimer();
    this._listeners = {};
    this._destroyed = true;
  }


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

    //  lw 3amalna advance lel step elly howa already the last step, el status byet3adal le complete w no further steps are fired. w enna el events eli byetfire ma3a kol step b sah w consistent ma3a the step object w index.
    if (this._index === this._steps.length - 1) {
      this._setStatus('complete');
      return;
    }

    // di el pauseOnKeySteps option, lw howa true w el step el gedid howa key step, auto-play byetwa2af immediately w consistent ma3 the status being 'paused'. w enna el events eli byetfire ma3a kol step b sah w consistent ma3 the step object w index.
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
 // hena el focus controller byet2aked en el sequencing sah w consistent ma3a the steps eli byet2adem laha, w enna el highlighted nodes for each step are correctly applied to the DOM with the appropriate opacity and transitions. w akid en el restoreAll method restores all nodes to full opacity consistently, w enna el destroy method nulls out references without affecting the DOM elements (which are managed by NodeRenderer's exit transitions).
  _scheduleNext() {
    if (this._status !== 'playing') return;
    if (this._index >= this._steps.length - 1) {
      this._setStatus('complete');
      return;
    }

    // el timing of the auto-play is consistent ma3 the speed property w the pauseOnKeySteps option (e.g. if pauseOnKeySteps is true, auto-play should pause immediately upon landing on a key step). w akid en el public API methods (play, pause, stepForward, stepBack, seekTo, setSpeed) byet2aked enhom byet3amaloo el expected behavior consistently. w akid kaman en el destroy method byet2aked enha btetnada sah w consistent ma3a the destroyed state (e.g. after destroy is called, no further events should fire and all methods should be no-ops).
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
        // lw el callback fe error, we catch it to prevent the entire playback controller from breaking, w log the error for debugging. w akid en el error message should be clear enough to identify which event listener caused the issue.
        console.error(`PlaybackController: error in '${event}' listener:`, err);
      }
    }
  }
}

module.exports = { PlaybackController };
