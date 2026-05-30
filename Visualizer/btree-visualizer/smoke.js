const { AnimationLayer } = require('./src/animation/AnimationLayer');
const { PlaybackController } = require('./src/playback/PlaybackController');
const { insert } = require('./src/core/insert');
const { deleteKey } = require('./src/core/delete');
const { search } = require('./src/core/search');
const { createTree } = require('./src/core/BTree');
const d3 = require('d3');

const svgEl = document.getElementById('svg');
if (!svgEl) {
  throw new Error('Missing <svg id="svg"> in index.html');
}

const anim = new AnimationLayer(svgEl, d3);

const statusEl = document.createElement('div');
statusEl.style.cssText = [
  'position: fixed',
  'left: 12px',
  'bottom: 12px',
  'padding: 8px 12px',
  'border-radius: 999px',
  'background: rgba(25, 25, 25, 0.86)',
  'color: #f5f2ea',
  'font: 13px/1.3 Georgia, serif',
  'border: 1px solid rgba(255, 215, 128, 0.25)',
  'box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35)',
  'z-index: 20',
].join('; ');
statusEl.textContent = 'B-tree smoke demo starting...';
document.body.appendChild(statusEl);

const demoOps = [
  { type: 'insert', key: 10 },
  { type: 'insert', key: 20 },
  { type: 'insert', key: 30 },
  { type: 'insert', key: 40 },
  { type: 'insert', key: 50 },
  { type: 'insert', key: 5 },
  { type: 'insert', key: 15 },
  { type: 'insert', key: 25 },
  { type: 'search', key: 25 },
  { type: 'search', key: 999 },
  { type: 'insert', key: 60 },
  { type: 'insert', key: 70 },
  { type: 'insert', key: 80 },
  { type: 'search', key: 40 },
  { type: 'delete', key: 5 },
  { type: 'delete', key: 15 },
  { type: 'delete', key: 20 },
  { type: 'insert', key: 12 },
  { type: 'insert', key: 18 },
  { type: 'search', key: 18 },
  { type: 'delete', key: 25 },
  { type: 'delete', key: 30 },
  { type: 'insert', key: 22 },
  { type: 'insert', key: 27 },
  { type: 'search', key: 27 },
  { type: 'delete', key: 40 },
];

let state = createTree(2);
let activeController = null;

function runOperation(index) {
  if (index >= demoOps.length) {
    statusEl.textContent = 'Demo complete. Reload the page to replay it.';
    anim.fitView(state);
    return;
  }

  const op = demoOps[index];
  statusEl.textContent = `${index + 1}/${demoOps.length}: ${op.type} ${op.key}`;

  let steps;
  if (op.type === 'insert') {
    steps = insert(state, op.key);
  } else if (op.type === 'search') {
    steps = search(state, op.key);
  } else {
    steps = deleteKey(state, op.key);
  }

  state = steps[steps.length - 1].state;

  if (activeController) {
    activeController.destroy();
    activeController = null;
  }

  activeController = new PlaybackController(steps, {
    speed: 1.4,
    pauseOnKeySteps: false,
    msPerStep: 360,
  });

  activeController.on('frame', (step) => anim.render(step));
  activeController.on('statusChange', ({ status }) => {
    if (status === 'complete') {
      anim.fitView(state);
      setTimeout(() => runOperation(index + 1), 450);
    }
  });

  anim.fitView(state);
  activeController.play();
}

runOperation(0);
