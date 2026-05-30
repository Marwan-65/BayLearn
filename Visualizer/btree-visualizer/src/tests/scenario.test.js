// Stage 9 Tests --, Scenario Mode
//
// Covers:
//   1. scenarios.js  --, data shape, all required fields present, t/keys valid
//   2. ScenarioRunner --, event sequencing, op chaining, stop/cancel, error handling
//
// All pure Node --, no DOM, no jsdom, no d3 needed.
//
// Run:
//   node src/tests/scenario.test.js

'use strict';

const { test, suite, summary, eq, ok, throws } = require('./runner');
const { SCENARIOS, SCENARIO_MAP } = require('../scenarios/scenarios');
const { ScenarioRunner }          = require('../scenarios/ScenarioRunner');

// ─────────────────────────────────────────────────────────────────────────────
// Section 1 --, scenarios.js data validation
// ─────────────────────────────────────────────────────────────────────────────

suite('scenarios.js --, data shape', () => {
  test('SCENARIOS is a non-empty array', () => {
    ok(Array.isArray(SCENARIOS) && SCENARIOS.length > 0);
  });

  test('SCENARIO_MAP has the same entries as SCENARIOS', () => {
    eq(Object.keys(SCENARIO_MAP).length, SCENARIOS.length);
    for (const sc of SCENARIOS) {
      ok(SCENARIO_MAP[sc.id] !== undefined, `SCENARIO_MAP missing id "${sc.id}"`);
    }
  });

  test('every scenario has required fields', () => {
    const required = ['id', 'name', 'description', 't', 'initialKeys', 'operations'];
    for (const sc of SCENARIOS) {
      for (const field of required) {
        ok(sc[field] !== undefined, `Scenario "${sc.id}" missing field "${field}"`);
      }
    }
  });

  test('all scenario ids are unique strings', () => {
    const ids = SCENARIOS.map(s => s.id);
    const unique = new Set(ids);
    eq(unique.size, ids.length, 'scenario IDs must be unique');
    for (const id of ids) {
      ok(typeof id === 'string' && id.length > 0, `id "${id}" must be a non-empty string`);
    }
  });

  test('all t values are integers in range [2, 5]', () => {
    for (const sc of SCENARIOS) {
      ok(Number.isInteger(sc.t), `"${sc.id}" t must be an integer`);
      ok(sc.t >= 2 && sc.t <= 5,  `"${sc.id}" t=${sc.t} is outside [2,5]`);
    }
  });

  test('initialKeys are arrays of positive integers', () => {
    for (const sc of SCENARIOS) {
      ok(Array.isArray(sc.initialKeys), `"${sc.id}" initialKeys must be an array`);
      for (const k of sc.initialKeys) {
        ok(Number.isInteger(k) && k > 0, `"${sc.id}" initialKey ${k} must be a positive integer`);
      }
    }
  });

  test('operations are arrays of {op, key} objects', () => {
    for (const sc of SCENARIOS) {
      ok(Array.isArray(sc.operations) && sc.operations.length > 0,
        `"${sc.id}" operations must be a non-empty array`);
      for (const op of sc.operations) {
        ok(['search', 'insert', 'delete'].includes(op.op),
          `"${sc.id}" operation op "${op.op}" must be search/insert/delete`);
        ok(Number.isInteger(op.key) && op.key > 0,
          `"${sc.id}" operation key ${op.key} must be a positive integer`);
      }
    }
  });

  test('all names and descriptions are non-empty strings', () => {
    for (const sc of SCENARIOS) {
      ok(typeof sc.name === 'string' && sc.name.length > 0,
        `"${sc.id}" name must be a non-empty string`);
      ok(typeof sc.description === 'string' && sc.description.length > 10,
        `"${sc.id}" description is too short`);
    }
  });

  test('pauseMs is a positive number when present', () => {
    for (const sc of SCENARIOS) {
      if (sc.pauseMs !== undefined) {
        ok(typeof sc.pauseMs === 'number' && sc.pauseMs > 0,
          `"${sc.id}" pauseMs must be a positive number`);
      }
    }
  });
});

suite('scenarios.js --, named scenario content', () => {
  test('db-index scenario exists and uses t=3', () => {
    const sc = SCENARIO_MAP['db-index'];
    ok(sc !== undefined, 'db-index scenario should exist');
    eq(sc.t, 3);
    ok(sc.operations.length >= 10, 'db-index should have at least 10 operations');
    ok(sc.operations.every(o => o.op === 'insert'), 'db-index should be all inserts');
  });

  test('split-cascade starts with a full leaf tree', () => {
    const sc = SCENARIO_MAP['split-cascade'];
    ok(sc !== undefined);
    eq(sc.t, 2);
    ok(sc.initialKeys.length > 0, 'split-cascade needs pre-built initial keys');
    ok(sc.operations.every(o => o.op === 'insert'));
  });

  test('merge-cascade uses delete operations', () => {
    const sc = SCENARIO_MAP['merge-cascade'];
    ok(sc !== undefined);
    ok(sc.operations.every(o => o.op === 'delete'), 'merge-cascade should be all deletes');
  });

  test('borrow scenario has exactly 2 operations', () => {
    const sc = SCENARIO_MAP['borrow'];
    ok(sc !== undefined);
    eq(sc.operations.length, 2);
    ok(sc.operations.every(o => o.op === 'delete'));
  });

  test('balanced scenario has both inserts and deletes', () => {
    const sc = SCENARIO_MAP['balanced'];
    ok(sc !== undefined);
    const hasInserts = sc.operations.some(o => o.op === 'insert');
    const hasDeletes = sc.operations.some(o => o.op === 'delete');
    ok(hasInserts, 'balanced should have inserts');
    ok(hasDeletes, 'balanced should have deletes');
  });

  test('all initialKeys in all scenarios are unique within each scenario', () => {
    for (const sc of SCENARIOS) {
      const unique = new Set(sc.initialKeys);
      eq(unique.size, sc.initialKeys.length,
        `"${sc.id}" initialKeys should not have duplicates`);
    }
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Section 2 --, ScenarioRunner
// ─────────────────────────────────────────────────────────────────────────────

// Build a simple mock scenario and a mock startOp factory that returns a
// minimal PlaybackController-like object.
function makeMockCtrl() {
  const listeners = {};
  return {
    on(event, fn)  { if (!listeners[event]) listeners[event] = []; listeners[event].push(fn); },
    off(event, fn) { if (listeners[event]) listeners[event] = listeners[event].filter(f => f !== fn); },
    fire(event, data) { (listeners[event] ?? []).forEach(fn => fn(data)); },
  };
}

function makeScenario(ops, overrides = {}) {
  return {
    id:          'test',
    name:        'Test Scenario',
    description: 'A test scenario.',
    t:           2,
    initialKeys: [],
    operations:  ops,
    pauseMs:     0,  // no delay in tests
    ...overrides,
  };
}

function makeRunner(ops, cbs = {}, startOpFn = null) {
  const ctrls = [];
  const startOp = startOpFn ?? ((op, key) => {
    const c = makeMockCtrl();
    ctrls.push({ ctrl: c, op, key });
    return c;
  });
  const scenario = makeScenario(ops);
  const runner   = new ScenarioRunner(scenario, cbs, startOp);
  return { runner, ctrls };
}

suite('ScenarioRunner --, construction', () => {
  test('constructs without throwing', () => {
    const { runner } = makeRunner([{ op: 'insert', key: 10 }]);
    ok(runner !== null);
  });

  test('totalOperations matches scenario ops length', () => {
    const { runner } = makeRunner([
      { op: 'insert', key: 10 },
      { op: 'insert', key: 20 },
      { op: 'delete', key: 10 },
    ]);
    eq(runner.totalOperations, 3);
  });

  test('isRunning is false before start()', () => {
    const { runner } = makeRunner([{ op: 'insert', key: 10 }]);
    eq(runner.isRunning, false);
  });

  test('currentIndex starts at 0', () => {
    const { runner } = makeRunner([{ op: 'insert', key: 10 }]);
    eq(runner.currentIndex, 0);
  });
});

suite('ScenarioRunner --, single operation', () => {
  test('start() calls startOp with correct op and key', () => {
    const calls = [];
    const { runner, ctrls } = makeRunner(
      [{ op: 'insert', key: 42 }],
      {},
      (op, key) => { calls.push({ op, key }); return makeMockCtrl(); }
    );
    runner.start();
    eq(calls.length, 1);
    eq(calls[0].op,  'insert');
    eq(calls[0].key, 42);
  });

  test('onOperationStart fires with correct args', () => {
    const events = [];
    const { runner, ctrls } = makeRunner(
      [{ op: 'search', key: 5 }],
      { onOperationStart: (op, key, idx, total) => events.push({ op, key, idx, total }) }
    );
    runner.start();
    eq(events.length, 1);
    eq(events[0].op,    'search');
    eq(events[0].key,   5);
    eq(events[0].idx,   0);
    eq(events[0].total, 1);
  });

  test('onOperationEnd fires when controller emits complete', () => {
    const ended = [];
    const { runner, ctrls } = makeRunner(
      [{ op: 'delete', key: 99 }],
      { onOperationEnd: (op, key, idx, total) => ended.push({ op, key, idx, total }) }
    );
    runner.start();
    eq(ended.length, 0, 'should not fire before complete');

    ctrls[0].ctrl.fire('statusChange', { status: 'complete' });
    eq(ended.length, 1);
    eq(ended[0].op,  'delete');
    eq(ended[0].key, 99);
  });

  test('onComplete fires after the last operation completes', () => {
    let completed = false;
    const { runner, ctrls } = makeRunner(
      [{ op: 'insert', key: 1 }],
      { onComplete: () => { completed = true; } }
    );
    runner.start();
    eq(completed, false);
    ctrls[0].ctrl.fire('statusChange', { status: 'complete' });
    eq(completed, true);
  });
});

suite('ScenarioRunner --, multiple operations', () => {
  test('chains two operations in sequence', () => {
    const started = [];
    const { runner, ctrls } = makeRunner(
      [{ op: 'insert', key: 10 }, { op: 'insert', key: 20 }],
      { onOperationStart: (op, key) => started.push({ op, key }) }
    );
    runner.start();
    eq(started.length, 1, 'only first op should start before first completes');
    eq(started[0].key, 10);

    ctrls[0].ctrl.fire('statusChange', { status: 'complete' });
    eq(started.length, 2, 'second op should start after first completes');
    eq(started[1].key, 20);
  });

  test('onAnnounce fires between operations', () => {
    const announces = [];
    const { runner, ctrls } = makeRunner(
      [{ op: 'insert', key: 10 }, { op: 'delete', key: 10 }],
      { onAnnounce: (msg) => announces.push(msg) }
    );
    runner.start();
    ctrls[0].ctrl.fire('statusChange', { status: 'complete' });
    eq(announces.length, 1);
    ok(announces[0].includes('Delete') || announces[0].includes('delete'),
      `announce message should mention the next op: "${announces[0]}"`);
    ok(announces[0].includes('10'), 'announce should include the next key');
  });

  test('onProgressUpdate fires for each operation', () => {
    const updates = [];
    const { runner, ctrls } = makeRunner(
      [{ op: 'insert', key: 1 }, { op: 'insert', key: 2 }, { op: 'insert', key: 3 }],
      { onProgressUpdate: (idx, total) => updates.push({ idx, total }) }
    );
    runner.start();
    eq(updates[0].total, 3);

    ctrls[0].ctrl.fire('statusChange', { status: 'complete' });
    ctrls[1].ctrl.fire('statusChange', { status: 'complete' });
    ctrls[2].ctrl.fire('statusChange', { status: 'complete' });

    ok(updates.length >= 3, 'should have at least one update per operation');
  });

  test('onComplete fires only once, after all three ops', () => {
    let completions = 0;
    const { runner, ctrls } = makeRunner(
      [{ op: 'insert', key: 1 }, { op: 'insert', key: 2 }, { op: 'insert', key: 3 }],
      { onComplete: () => completions++ }
    );
    runner.start();
    ctrls[0].ctrl.fire('statusChange', { status: 'complete' });
    ctrls[1].ctrl.fire('statusChange', { status: 'complete' });
    eq(completions, 0, 'should not complete before all ops done');
    ctrls[2].ctrl.fire('statusChange', { status: 'complete' });
    eq(completions, 1, 'should complete exactly once');
  });

  test('intermediate status changes (playing, paused) do not trigger next op', () => {
    const started = [];
    const { runner, ctrls } = makeRunner(
      [{ op: 'insert', key: 10 }, { op: 'insert', key: 20 }],
      { onOperationStart: (op, key) => started.push(key) }
    );
    runner.start();
    ctrls[0].ctrl.fire('statusChange', { status: 'playing' });
    ctrls[0].ctrl.fire('statusChange', { status: 'paused' });
    eq(started.length, 1, 'non-complete statuses should not advance to next op');

    ctrls[0].ctrl.fire('statusChange', { status: 'complete' });
    eq(started.length, 2);
  });
});

suite('ScenarioRunner --, stop() cancellation', () => {
  test('stop() before start() makes isRunning false', () => {
    const { runner } = makeRunner([{ op: 'insert', key: 1 }]);
    runner.stop();
    eq(runner.isRunning, false);
  });

  test('stop() after start() prevents second op from starting', () => {
    const started = [];
    const { runner, ctrls } = makeRunner(
      [{ op: 'insert', key: 10 }, { op: 'insert', key: 20 }],
      { onOperationStart: (op, key) => started.push(key) }
    );
    runner.start();
    runner.stop();
    ctrls[0].ctrl.fire('statusChange', { status: 'complete' });
    eq(started.length, 1, 'second op should not start after stop()');
  });

  test('stop() prevents onComplete from firing', () => {
    let completed = false;
    const { runner, ctrls } = makeRunner(
      [{ op: 'insert', key: 1 }],
      { onComplete: () => { completed = true; } }
    );
    runner.start();
    runner.stop();
    ctrls[0].ctrl.fire('statusChange', { status: 'complete' });
    eq(completed, false, 'onComplete should not fire after stop()');
  });

  test('isRunning is false after stop()', () => {
    const { runner } = makeRunner([{ op: 'insert', key: 1 }, { op: 'insert', key: 2 }]);
    runner.start();
    runner.stop();
    eq(runner.isRunning, false);
  });
});

suite('ScenarioRunner --, startOp returning null (error case)', () => {
  test('runner stops gracefully when startOp returns null', () => {
    let completed = false;
    const runner = new ScenarioRunner(
      makeScenario([{ op: 'insert', key: 10 }]),
      { onComplete: () => { completed = true; } },
      () => null  // simulates an error in operation execution
    );
    runner.start();
    eq(runner.isRunning, false, 'runner should stop if startOp returns null');
    eq(completed, false, 'onComplete should not fire after error');
  });
});

suite('ScenarioRunner --, callback robustness', () => {
  test('runner works with no callbacks provided', () => {
    const { runner, ctrls } = makeRunner([{ op: 'insert', key: 5 }], {});
    runner.start();
    ctrls[0].ctrl.fire('statusChange', { status: 'complete' });
    ok(true, 'should not throw with empty callbacks');
  });

  test('all callbacks are optional individually', () => {
    const { runner, ctrls } = makeRunner(
      [{ op: 'insert', key: 1 }, { op: 'delete', key: 1 }],
      { onOperationStart: (op) => ok(true) } // only one provided
    );
    runner.start();
    ctrls[0].ctrl.fire('statusChange', { status: 'complete' });
    ctrls[1].ctrl.fire('statusChange', { status: 'complete' });
    ok(true);
  });
});

// ─────────────────────────────────────────────────────────────────────────────

summary();
process.exit(0);
