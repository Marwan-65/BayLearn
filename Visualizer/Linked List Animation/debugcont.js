import { fromArray, insertAtHead, INSERT_AT_HEAD_PSEUDOCODE } from './index.js';

import { PlaybackController } from './playback/PlaybackController.js';

const steps = insertAtHead(fromArray([2, 3, 4]), 1);
const ctrl  = new PlaybackController(steps);

ctrl.on('frame',     step => console.log(`[ANIMATION] render step ${step.stepIndex}, highlights: ${JSON.stringify(step.highlights)}`));
ctrl.on('narrative', step => console.log(`[NARRATIVE] "${step.explanation.slice(0, 60)}..."`));
ctrl.on('statusChange', p => console.log(`[STATUS] ${p.status}  ${p.currentIndex}/${p.totalSteps}`));
ctrl.on('complete', () => console.log('[DONE]'));

// Manually step through
ctrl.stepForward();
ctrl.stepForward();
ctrl.stepBack();

// Or auto-play (completes asynchronously)
ctrl.setSpeed(3);
ctrl.play();