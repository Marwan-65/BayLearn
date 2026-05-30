// Minimal test runner. Zero dependencies --, just Node.js assert.
// Usage: require('./runner') and call test(), pass(), fail() etc.

const assert = require('assert');

let _total = 0;
let _passed = 0;
let _failed = 0;
const _failures = [];

function test(name, fn) {
  _total++;
  try {
    fn();
    _passed++;
    process.stdout.write(`  ✓ ${name}\n`);
  } catch (err) {
    _failed++;
    _failures.push({ name, err });
    process.stdout.write(`  ✗ ${name}\n    ${err.message}\n`);
  }
}

function suite(name, fn) {
  process.stdout.write(`\n${name}\n${'─'.repeat(name.length)}\n`);
  fn();
}

function summary() {
  process.stdout.write(`\n${_passed}/${_total} passed`);
  if (_failed > 0) {
    process.stdout.write(`, ${_failed} failed\n`);
    process.exit(1);
  } else {
    process.stdout.write(` --, all good\n`);
  }
}

// Convenience wrappers around assert so tests read naturally
function eq(actual, expected, msg) {
  assert.deepStrictEqual(actual, expected, msg);
}

function ok(val, msg) {
  assert.ok(val, msg);
}

function throws(fn, msg) {
  assert.throws(fn, msg);
}

module.exports = { test, suite, summary, eq, ok, throws };