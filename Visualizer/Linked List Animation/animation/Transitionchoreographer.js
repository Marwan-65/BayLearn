

import { ACTIONS } from '../schema/index.js';


export function plan(prevStep, currentStep, theme) {
  const t      = theme.t;
  const action = currentStep.action;

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

    case ACTIONS.CREATE_NODE:
      return { ...defaults,
        nodeEnter:  { delay: 0,   duration: t.nodeEnter },
        arrowEnter: { delay: t.nodeEnter * 0.6, duration: t.arrowEnter },
      };

    case ACTIONS.SET_NEW_NEXT:
    case ACTIONS.ATTACH_TO_TAIL:
    case ACTIONS.WIRE_NEW_NODE:
      return { ...defaults,
        colorChange:  { delay: 0,   duration: t.colorChange  },
        arrowEnter:   { delay: 150, duration: t.arrowEnter   },
        arrowReroute: { delay: 150, duration: t.arrowReroute },
      };

    case ACTIONS.UPDATE_HEAD:
    case ACTIONS.ADVANCE_HEAD:
    case ACTIONS.UPDATE_HEAD_TO_PREV:
      return { ...defaults,
        headLabel:   { delay: 0,   duration: t.headLabel   },
        colorChange: { delay: 100, duration: t.colorChange },
        arrowExit:   { delay: 0,   duration: t.arrowExit   },
        arrowEnter:  { delay: 100, duration: t.arrowEnter  },
      };

    case ACTIONS.BYPASS_NODE:
    case ACTIONS.REMOVE_NODE:
      return { ...defaults,
        arrowReroute: { delay: 0,   duration: t.arrowReroute },
        nodeExit:     { delay: 100, duration: t.nodeExit     },
      };

    case ACTIONS.ADVANCE_CURRENT:
    case ACTIONS.VISIT_NODE:
    case ACTIONS.SET_CURRENT_TO_HEAD:
      return { ...defaults,
        colorChange:  { delay: 0,   duration: t.colorChange  },
        arrowEnter:   { delay: 0,   duration: t.arrowEnter   },
      };

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