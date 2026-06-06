
import { getOrderedIds } from '../schema/index.js';


export function computeHorizontalLayout(state, theme) {
  const orderedIds = getOrderedIds(state);
  const nodeW      = theme.nodeValueW + theme.nodeNextW;
  const step       = nodeW + theme.nodeGap;
  const positions  = {};

  orderedIds.forEach((id, i) => {
    positions[id] = {
      x: 80 + i * step + nodeW / 2,   
      y: theme.rowY,
    };
  });

  return positions;
}