/**
 * ANIMATION / TRANSITION CHOREOGRAPHER
 *
 * Decides HOW state changes are animated --, the sequencing and timing
 * of individual D3 transitions.
 *
 * Without this, everything animates simultaneously, which is confusing.
 * The choreographer ensures that, for example, on INSERT:
 *   1. New node fades in first
 *   2. Then the new pointer appears
 *   3. Then the old pointer re-routes
 *   4. Then the head label updates
 *
 * Returns a "plan" object consumed by the renderers.
 * Each plan property is a { delay, duration } pair.
 */

import { ACTIONS } from '../schema/index.js';

/**
 * @typedef  {object} ChoreographyPlan
 * @property {{ delay: number, duration: number }} nodeEnter
 * @property {{ delay: number, duration: number }} nodeExit
 * @property {{ delay: number, duration: number }} nodeMove
 * @property {{ delay: number, duration: number }} colorChange
 * @property {{ delay: number, duration: number }} arrowEnter
 * @property {{ delay: number, duration: number }} arrowExit
 * @property {{ delay: number, duration: number }} arrowReroute
 * @property {{ delay: number, duration: number }} headLabel
 */

/**
 * Returns a choreography plan for the transition from prevStep → currentStep.
 *
 * @param {Step|null} prevStep
 * @param {Step}      currentStep
 * @param {object}    theme        - theme.t timing constants
 * @returns {ChoreographyPlan}
 */
export function plan(prevStep, currentStep, theme) {
  const t      = theme.t;
  const action = currentStep.action;

  // Default plan --, everything simultaneous at the base timings
  const defaults = {
    nodeEnter:    { delay: 0,   duration: t.nodeEnter    },
    nodeExit:     { delay: 0,   duration: t.nodeExit     },
    nodeMove:     { delay: 0,   duration: t.nodeMove     },
    colorChange:  { delay: 0,   duration: t.colorChange  },
    arrowEnter:   { delay: 0,   duration: t.arrowEnter   },
    arrowExit:    { delay: 0,   duration: t.arrowExit    },
    arrowReroute: { delay: 0,   duration: t.arrowReroute },
    headLabel:    { delay: 0,   duration: t.headLabel    },
  };

  switch (action) {

    // ── Node creation: node first, then arrow ─────────────────────────────
    case ACTIONS.CREATE_NODE:
      return { ...defaults,
        nodeEnter:  { delay: 0,   duration: t.nodeEnter },
        arrowEnter: { delay: t.nodeEnter * 0.6, duration: t.arrowEnter },
      };

    // ── Wiring: show new pointer after a beat ─────────────────────────────
    case ACTIONS.SET_NEW_NEXT:
    case ACTIONS.ATTACH_TO_TAIL:
    case ACTIONS.WIRE_NEW_NODE:
      return { ...defaults,
        colorChange:  { delay: 0,   duration: t.colorChange  },
        arrowEnter:   { delay: 150, duration: t.arrowEnter   },
        arrowReroute: { delay: 150, duration: t.arrowReroute },
      };

    // ── Head update: move label, then recolour ────────────────────────────
    case ACTIONS.UPDATE_HEAD:
    case ACTIONS.ADVANCE_HEAD:
    case ACTIONS.UPDATE_HEAD_TO_PREV:
      return { ...defaults,
        headLabel:   { delay: 0,   duration: t.headLabel   },
        colorChange: { delay: 100, duration: t.colorChange },
        arrowExit:   { delay: 0,   duration: t.arrowExit   },
        arrowEnter:  { delay: 100, duration: t.arrowEnter  },
      };

    // ── Deletion: fade out node, then reroute arrow ───────────────────────
    case ACTIONS.BYPASS_NODE:
    case ACTIONS.REMOVE_NODE:
      return { ...defaults,
        arrowReroute: { delay: 0,   duration: t.arrowReroute },
        nodeExit:     { delay: 100, duration: t.nodeExit     },
      };

    // ── Traversal: colour change is the main event ────────────────────────
    case ACTIONS.ADVANCE_CURRENT:
    case ACTIONS.VISIT_NODE:
    case ACTIONS.SET_CURRENT_TO_HEAD:
      return { ...defaults,
        colorChange:  { delay: 0,   duration: t.colorChange  },
        arrowEnter:   { delay: 0,   duration: t.arrowEnter   },
      };

    // ── Pointer reversal: first save, then flip ───────────────────────────
    case ACTIONS.SAVE_NEXT:
      return { ...defaults,
        colorChange:  { delay: 0,   duration: t.colorChange  },
      };

    case ACTIONS.REVERSE_POINTER:
      return { ...defaults,
        arrowExit:    { delay: 0,   duration: t.arrowExit    },
        arrowEnter:   { delay: t.arrowExit, duration: t.arrowEnter },
        colorChange:  { delay: 0,   duration: t.colorChange  },
      };

    default:
      return defaults;
  }
}