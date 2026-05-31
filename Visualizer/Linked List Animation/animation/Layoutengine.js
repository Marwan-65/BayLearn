/**
 * ANIMATION / LAYOUT ENGINE
 *
 * Pure function --, takes a ListState and returns a positions map.
 * No side effects, no DOM, no D3.
 *
 * Keeping this separate means you can swap layouts (horizontal,
 * vertical, circular, memory-scattered) without touching any renderer.
 */

import { getOrderedIds } from '../schema/index.js';

/**
 * Horizontal layout --, nodes spaced evenly along a single row.
 *
 * @param {ListState} state
 * @param {object}    theme  - needs nodeValueW, nodeNextW, nodeGap, rowY
 * @returns {{ [nodeId: string]: { x: number, y: number } }}
 *
 * x is the CENTRE of the full node (value + next sections combined).
 * y is the CENTRE of the node row.
 */
export function computeHorizontalLayout(state, theme) {
  const orderedIds = getOrderedIds(state);
  const nodeW      = theme.nodeValueW + theme.nodeNextW;
  const step       = nodeW + theme.nodeGap;
  const positions  = {};

  orderedIds.forEach((id, i) => {
    positions[id] = {
      x: 80 + i * step + nodeW / 2,   // 80px left margin + centre offset
      y: theme.rowY,
    };
  });

  return positions;
}