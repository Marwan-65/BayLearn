//di the tests for the playback controller, el tests di byet2aked en el PlaybackController byet5adem 3ala el schema el sah w byet2aked en el status transitions sah w consistent w kaman en kol step //object elly byerga3ha el controller howa snapshot immutable w m4 hayet2asar b ay mutation ba3d shu76sh  keda
import assert from 'node:assert/strict';
import { PlaybackController, STATUS } from '../playback/PlaybackController.js';
import { fromArray, insertAtHead, reverse, traverse } from '../index.js';

let passed = 0;
let failed = 0;
// el main test function
function test(name, fn) {
  try {
    fn();
    console.log(`  PASS  ${name}`);
    passed++;
  } catch (err) {
    console.error(`  FAIL  ${name}`);
    console.error(`       ${err.message}`);
    failed++;
  }
}

async function testAsync(name, fn) {
  try {
    await fn();
    console.log(`  PASS  ${name}`);
    passed++;
  } catch (err) {
    console.error(`  FAIL  ${name}`);
    console.error(`       ${err.message}`);
    failed++;
  }
}

function section(title) {
  console.log(`\n── ${title} ${'─'.repeat(50 - title.length)}`);
}

function makeCtrl(options = {}) {
  const steps = insertAtHead(fromArray([2, 3, 4]), 1);
  return { ctrl: new PlaybackController(steps, options), steps };
}

//el section da by taregt el construction w el initial properties of the PlaybackController, we check en el steps array elly byet2adem lel constructor m4 fadi w en el properties elly byet3araf beha el controller zay el status w el currentIndex w el totalSteps w el currentStep sah w consistent ma3 el steps array.
section('Construction');

test('throws on empty steps array', () => {
  assert.throws(() => new PlaybackController([]), /non-empty/);
});

test('initial status is IDLE', () => {
  const { ctrl } = makeCtrl();
  assert.equal(ctrl.status, STATUS.IDLE);
});

test('initial index is 0', () => {
  const { ctrl } = makeCtrl();
  assert.equal(ctrl.currentIndex, 0);
});

test('totalSteps matches steps array length', () => {
  const { ctrl, steps } = makeCtrl();
  assert.equal(ctrl.totalSteps, steps.length);
});

test('currentStep returns step 0 initially', () => {
  const { ctrl, steps } = makeCtrl();
  assert.deepEqual(ctrl.currentStep, steps[0]);
});

// els section da by taregt el navigation functions stepForward w stepBack w jumpTo w jumpToEnd w rewind, we check en kol wa7da menhom btet2aked en el index bet3ada b sah w consistent ma3 el totalSteps w en el index m4 hayet2asar b ay overflow aw underflow w en el status betet3araf beha sah w consistent ma3 el navigation state (e.g. m4 momken a3mel stepForward lw ana already at the end).
section('Navigation --, stepForward / stepBack / jumpTo');

test('stepForward advances index by 1', () => {
  const { ctrl } = makeCtrl();
  ctrl.stepForward();
  assert.equal(ctrl.currentIndex, 1);
});

test('stepForward at end does not overflow', () => {
  const { ctrl } = makeCtrl();
  ctrl.jumpToEnd();
  const idxBefore = ctrl.currentIndex;
  ctrl.stepForward();
  assert.equal(ctrl.currentIndex, idxBefore);
});

test('stepBack decrements index by 1', () => {
  const { ctrl } = makeCtrl();
  ctrl.stepForward();
  ctrl.stepForward();
  ctrl.stepBack();
  assert.equal(ctrl.currentIndex, 1);
});

test('stepBack at start does not underflow', () => {
  const { ctrl } = makeCtrl();
  ctrl.stepBack();
  assert.equal(ctrl.currentIndex, 0);
});

test('jumpTo clamps to valid range', () => {
  const { ctrl } = makeCtrl();
  ctrl.jumpTo(9999);
  assert.equal(ctrl.currentIndex, ctrl.totalSteps - 1);
  ctrl.jumpTo(-5);
  assert.equal(ctrl.currentIndex, 0);
});

test('rewind returns to index 0 with IDLE status', () => {
  const { ctrl } = makeCtrl();
  ctrl.stepForward();
  ctrl.stepForward();
  ctrl.rewind();
  assert.equal(ctrl.currentIndex, 0);
  assert.equal(ctrl.status, STATUS.IDLE);
});

test('jumpToEnd reaches last step', () => {
  const { ctrl } = makeCtrl();
  ctrl.jumpToEnd();
  assert.equal(ctrl.currentIndex, ctrl.totalSteps - 1);
  assert.equal(ctrl.isAtEnd, true);
});

// el section da byet2aked en el key step navigation functions nextKeyStep w prevKeyStep byet2aked enhom byet7arakoo sah w consistent ma3 el isKeyStep property of the steps w enhom byet5ademoo 3ala el correct subset of steps (i.e. only the key steps).
section('Key step navigation');

test('nextKeyStep jumps to next isKeyStep', () => {
  const { ctrl, steps } = makeCtrl();
  ctrl.nextKeyStep();
  const idx = ctrl.currentIndex;
  assert.ok(steps[idx].isKeyStep, `step ${idx} should be a key step`);
});

test('prevKeyStep jumps to previous isKeyStep', () => {
  const { ctrl, steps } = makeCtrl();
  ctrl.jumpToEnd();
  ctrl.prevKeyStep();
  const idx = ctrl.currentIndex;
  assert.ok(steps[idx].isKeyStep, `step ${idx} should be a key step`);
});

//el section da byet2aked en el progress property byet7asab sah w consistent ma3 el currentIndex w totalSteps, we check en el progress howa 0 at the start w 1 at the end w between 0 w 1 in the middle.
section('Progress');

test('progress is 0 at start', () => {
  const { ctrl } = makeCtrl();
  assert.equal(ctrl.progress, 0);
});

test('progress is 1 at end', () => {
  const { ctrl } = makeCtrl();
  ctrl.jumpToEnd();
  assert.equal(ctrl.progress, 1);
});

test('progress is between 0 and 1 in the middle', () => {
  const { ctrl } = makeCtrl();
  ctrl.jumpTo(Math.floor(ctrl.totalSteps / 2));
  assert.ok(ctrl.progress > 0 && ctrl.progress < 1);
});

// el section da byet2aked en el event system byet7akem sah w consistent, we check en el events elly byetfirew zay el frame w el narrative w el statusChange byetfirew b sah w consistent ma3 el navigation state w en el payload elly byetfire m3ahom sah w consistent ma3 el current step w current index, w kaman en el on() method byet7akem sah w byerga3 function unsubscribe w enha btet5adem sah.
section('Events --, frame / narrative / statusChange');

test('stepForward fires frame event with correct step', () => {
  const { ctrl, steps } = makeCtrl();
  let received = null;
  ctrl.on('frame', step => { received = step; });
  ctrl.stepForward();
  assert.deepEqual(received, steps[1]);
});

test('stepForward fires narrative event with correct step', () => {
  const { ctrl, steps } = makeCtrl();
  let received = null;
  ctrl.on('narrative', step => { received = step; });
  ctrl.stepForward();
  assert.deepEqual(received, steps[1]);
});

test('frame and narrative receive the same step object', () => {
  const { ctrl } = makeCtrl();
  let frameStep = null;
  let narrativeStep = null;
  ctrl.on('frame',     s => { frameStep = s; });
  ctrl.on('narrative', s => { narrativeStep = s; });
  ctrl.stepForward();
  assert.deepEqual(frameStep, narrativeStep);
});

test('statusChange fires with correct payload on stepForward', () => {
  const { ctrl } = makeCtrl();
  let payload = null;
  ctrl.on('statusChange', p => { payload = p; });
  ctrl.stepForward();
  assert.equal(payload.currentIndex, 1);
  assert.equal(payload.totalSteps, ctrl.totalSteps);
  assert.ok(typeof payload.progress === 'number');
});

test('on() returns unsubscribe function that works', () => {
  const { ctrl } = makeCtrl();
  let count = 0;
  const unsub = ctrl.on('frame', () => count++);
  ctrl.stepForward();
  assert.equal(count, 1);
  unsub();
  ctrl.stepForward();
  assert.equal(count, 1);
});

test('on() throws on unknown event', () => {
  const { ctrl } = makeCtrl();
  assert.throws(() => ctrl.on('invalid', () => {}), /Unknown event/);
});

// el section da byet2aked en el speed control byet7akem sah w consistent, we check en el setSpeed method byet3araf beha sah w byet7aded el speed property b sah w consistent ma3 el input, w kaman enha btet7akem fe el minimum speed (e.g. m4 momken a3ayen speed of 0 or negative).
section('Speed');

test('setSpeed updates speed property', () => {
  const { ctrl } = makeCtrl();
  ctrl.setSpeed(2.0);
  assert.equal(ctrl.speed, 2.0);
});

test('setSpeed clamps to minimum 0.1', () => {
  const { ctrl } = makeCtrl();
  ctrl.setSpeed(0);
  assert.equal(ctrl.speed, 0.1);
});

// el section da byet2aked en el loadSteps method byet7akem sah w consistent, we check enha btet2aked en el steps array elly byet2adem laha m4 fadi w enha btet2aked en el currentIndex w totalSteps w currentStep betet3araf beha sah w consistent ma3 el new steps array w kaman enha btetfire frame w narrative events b sah w consistent ma3 step 0 of the new steps array.
section('loadSteps');

test('loadSteps replaces steps and resets to 0', () => {
  const { ctrl } = makeCtrl();
  ctrl.stepForward();
  ctrl.stepForward();

  const newSteps = traverse(fromArray([10, 20]));
  ctrl.loadSteps(newSteps);

  assert.equal(ctrl.currentIndex, 0);
  assert.equal(ctrl.totalSteps, newSteps.length);
});

test('loadSteps fires frame and narrative with new step 0', () => {
  const { ctrl } = makeCtrl();
  const newSteps = reverse(fromArray([1, 2, 3]));
  let frameStep = null;
  ctrl.on('frame', s => { frameStep = s; });
  ctrl.loadSteps(newSteps);
  assert.deepEqual(frameStep, newSteps[0]);
});

test('loadSteps throws on empty array', () => {
  const { ctrl } = makeCtrl();
  assert.throws(() => ctrl.loadSteps([]), /non-empty/);
});

// el section da byet2aked en el play / pause / complete behavior byet7akem sah w consistent, we check en play() byet7arak sah w byetfire complete event at the end w en pause() byetwaqqaf sah w m4 hayet2asar b ay mutation ba3d keda
// also en play() after pause byet7arak men el index elly waqqafto 3aleh w en pauseOnKeySteps=true byetwaqqaf automatically at key steps. + en el play() byet7akem fe el speed property w en el timing of the auto-advance is consistent ma3 el speed (e.g. faster speed should result in faster completion). w kaman en el complete event byetfire b sah w consistent ma3 el final step w enha btetfire exactly once. w kaman en play() after complete does nothing. w kaman en pause() after complete does nothing.
section('Async --, play / pause / complete');

await testAsync('play() reaches complete and fires complete event', () => {
  return new Promise((resolve, reject) => {
    const steps = insertAtHead(fromArray([1]), 0);
    const ctrl  = new PlaybackController(steps, { speed: 50, pauseOnKeySteps: false });

    ctrl.on('complete', () => {
      try {
        assert.equal(ctrl.status, STATUS.DONE);
        assert.equal(ctrl.isAtEnd, true);
        ctrl.destroy();
        resolve();
      } catch (err) { reject(err); }
    });

    ctrl.play();
    setTimeout(() => reject(new Error('complete event never fired')), 3000);
  });
});

await testAsync('pause() stops auto-advance', () => {
  return new Promise((resolve, reject) => {
    const steps = insertAtHead(fromArray([2, 3, 4]), 1);
    const ctrl  = new PlaybackController(steps, { speed: 50, pauseOnKeySteps: false });

    ctrl.play();
    setTimeout(() => {
      ctrl.pause();
      const idxAtPause = ctrl.currentIndex;
      assert.equal(ctrl.status, STATUS.PAUSED);

      setTimeout(() => {
        try {
          assert.equal(ctrl.currentIndex, idxAtPause, 'index should not change after pause');
          ctrl.destroy();
          resolve();
        } catch (err) { reject(err); }
      }, 300);
    }, 150);

    setTimeout(() => reject(new Error('test timed out')), 3000);
  });
});

await testAsync('play() after pause() resumes from correct index', () => {
  return new Promise((resolve, reject) => {
    const steps = insertAtHead(fromArray([2, 3, 4, 5]), 1);
    const ctrl  = new PlaybackController(steps, { speed: 50, pauseOnKeySteps: false });
    let pausedAt = null;

    ctrl.on('statusChange', ({ status, currentIndex }) => {
      if (status === STATUS.PLAYING && pausedAt === null) {
        setTimeout(() => {
          ctrl.pause();
          pausedAt = ctrl.currentIndex;
          setTimeout(() => ctrl.play(), 50);
        }, 100);
      }

      if (status === STATUS.DONE) {
        try {
          assert.ok(pausedAt !== null, 'should have paused at some point');
          ctrl.destroy();
          resolve();
        } catch (err) { reject(err); }
      }
    });

    ctrl.play();
    setTimeout(() => reject(new Error('never completed')), 5000);
  });
});

await testAsync('pauseOnKeySteps=true auto-pauses at key steps', () => {
  return new Promise((resolve, reject) => {
    const steps = insertAtHead(fromArray([2, 3]), 1);
    const ctrl  = new PlaybackController(steps, { speed: 50, pauseOnKeySteps: true });
    let pauseCount = 0;

    ctrl.on('statusChange', ({ status, currentIndex }) => {
      if (status === STATUS.PAUSED) {
        pauseCount++;
        const step = steps[currentIndex];
        try {
          assert.equal(step.isKeyStep, true, `paused on non-key step ${currentIndex}`);
        } catch (err) { reject(err); return; }

        if (ctrl.isAtEnd) {
          ctrl.destroy();
          resolve();
        } else {
          setTimeout(() => ctrl.play(), 20);
        }
      }
    });

    ctrl.play();
    setTimeout(() => reject(new Error('test timed out')), 5000);
  });
});

// a5er section byet2aked en el destroy method byet7aken sa7 w consistent
section('destroy');

test('destroy clears all listeners', () => {
  const { ctrl } = makeCtrl();
  let count = 0;
  ctrl.on('frame', () => count++);
  ctrl.destroy();
  ctrl.stepForward();
  assert.equal(count, 0);
});

console.log(`\n${'═'.repeat(55)}`);
console.log(`  ${passed + failed} tests   PASS ${passed} passed   FAIL ${failed} failed`);
console.log(`${'═'.repeat(55)}\n`);

if (failed > 0) process.exit(1);