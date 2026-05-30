# B-Tree Visualizer Architecture Blueprint

This document specifies the full architecture, data contract, UI, animation system, and feature set for a B-tree visualizer that feels alive, explanatory, and deliberate.
It is inspired by the Linked List visualizer's strengths without copying its visuals.

---

## 1) Product Goals (Behavioral)

- Every frame should explain why a change happens, not just show the change.
- Animation is staged in meaningful sequences (choreography), not simultaneous updates.
- The UI directs attention to the active node/key and related structure.
- Playback allows both step-by-step learning and smooth full runs.

---

## 2) High-Level Layers

1) Data / Algorithm Layer
- Pure B-tree operations that emit a sequence of Steps.
- No DOM, no D3, no UI access.

2) Playback Layer
- Owns current step index, speed, and timing.
- Emits events for each step: "frame" and "narrative".

3) Animation Layer
- Renders the tree state to SVG/Canvas.
- Uses choreography plans to stage transitions.
- Handles camera pan/zoom and focus.

4) Narrative Layer
- Explainer text, pseudocode highlight, variable inspector, complexity panel.

5) UI Shell
- Inputs, playback controls, scenario loader, status indicators.

---

## 3) Core Data Model

### 3.1 B-Tree State

A snapshot for every step:

- t: integer (minimum degree)
- rootId: string
- nodes: map of nodeId -> node

Node:
- id: string
- keys: number[] (sorted)
- children: string[] (child node ids, length = keys.length + 1 if not leaf)
- isLeaf: boolean

Optional for layout:
- depth: integer (can be computed)

### 3.2 Step Schema (Critical)

Each algorithm action emits a Step object used by both animation and narrative layers:

- action: string
  Examples: SEARCH_VISIT, INSERT_KEY, SPLIT_NODE, PROMOTE_KEY,
  BORROW_LEFT, BORROW_RIGHT, MERGE_NODES, DELETE_KEY,
  REPLACE_WITH_PREDECESSOR, ROOT_REPLACE

- state: full B-tree state snapshot

- highlights:
  - nodes: [{ nodeId, role }]
  - keys: [{ nodeId, keyIndex, role }]
  - edges: [{ fromId, toId, role }]

- variables:
  - node
  - parent
  - key
  - index
  - t
  - leftSibling
  - rightSibling
  - childIndex

- explanation: string (short narrative sentence)
- pseudocodeLine: number (active line index)
- isKeyStep: boolean
- meta (optional):
  - reason: e.g., "overflow", "underflow", "rotate", "merge"
  - beforeAfter: boolean (if you want split pre/post snapshots)

---

## 4) Operations Coverage

Must support at least:
- Search
- Insert
- Delete
- Split
- Merge
- Borrow/Rotate
- Root replace on overflow/underflow

Every operation should emit steps with clear action types and explanations.

---

## 5) Animation System

### 5.1 Renderer Choice
- SVG recommended for crisp text, hover states, and easier transitions.
- D3 for data-driven transitions or custom animation engine.

### 5.2 Layout Engine
- Pure function: compute positions from state.
- Input: state + theme spacing rules.
- Output: map of nodeId -> { x, y }, key slot positions, edge paths.
- Tree layout: center parent over its children.

### 5.3 Choreography Plan
Each Step type maps to a timing plan so animations are staged:

Examples:
- INSERT_KEY
  1) highlight target node
  2) slide key into slot
  3) if overflow, pause and glow

- SPLIT_NODE
  1) highlight median key
  2) duplicate node shell into two
  3) move keys left/right
  4) promote median to parent

- BORROW_LEFT/BORROW_RIGHT
  1) highlight sibling + parent key
  2) move sibling key to parent
  3) move parent key into underflow node
  4) update child edge

- MERGE_NODES
  1) highlight both nodes and parent separator
  2) pull separator into left node
  3) move keys from right into left
  4) remove right node shell

Each plan returns per-element delays/durations:

- nodeEnter / nodeExit / nodeMove
- keyMove / keyEnter / keyExit
- edgeReroute / edgeEnter / edgeExit
- highlightFade
- cameraPan

### 5.4 Camera and Focus
- Auto-pan to keep active node centered.
- Optional smooth zoom to keep active subtree readable.
- Focus effect: dim non-active nodes to 0.4 opacity.

---

## 6) Narrative System

### 6.1 Explanation Panel
- Short sentence describing the action with the key reason.
- Example: "Node N3 overflowed (5 keys). Splitting and promoting 30."

### 6.2 Pseudocode Panel
- Operation-specific pseudocode lines.
- Highlight the current line using Step.pseudocodeLine.

### 6.3 Variable Inspector
- Chips for key variables: node, parent, key, index, siblings, t.
- Highlight changed variables with a flash.

### 6.4 Complexity Panel
- Show time complexity per operation.
- Note extra cost on split/merge or recursive descent.

---

## 7) UI/UX Shell

### 7.1 Top Bar
- Operation selector
- Key input
- t (minimum degree) selector
- Run button
- Scenario dropdown or Load JSON

### 7.2 Playback Controls
- Play / Pause
- Step forward/back
- Jump to next/prev key step
- Speed slider
- Progress bar with scrubbing

### 7.3 Status Badge
- Idle / Playing / Paused / Done
- Uses small indicator dot + label

---

## 8) Visual Design Principles

- Consistent visual tokens for roles (active, parent, sibling, split, etc.).
- Keys are in slots; active key has a distinct outline.
- Edges have subtle arrows or end caps to show direction.
- Root and leaf nodes have badges.
- Subtle grid background for depth and scale.

---

## 9) Theme / Tokens

Define reusable tokens:

- Colors: background, surface, border, text, accent, warning, success
- Fonts: UI font + mono for algorithm data
- Node sizes: node width by key count, slot width, slot height
- Edge styles: width, color, dashed for temporary edges
- Animation timings: base duration, stagger intervals

---

## 10) Scenario Mode

Allow a scenario JSON to define:

- initialTree (array or structured tree)
- operations: list of { op, key }

If a scenario is loaded, auto-play each operation with a small pause in between.

---

## 11) Implementation Plan (Order of Work)

1) Implement B-tree core + Step schema
2) Implement PlaybackController
3) Implement layout engine (static render)
4) Implement animation layer (transitions, focus)
5) Implement narrative layer
6) Wire UI shell
7) Add choreography plans per action
8) Add scenario mode

---

## 12) Testing & Validation

- Unit test: B-tree operations + step count + key invariants.
- Visual test: split, merge, borrow, root replace.
- Narrative test: pseudocode line matches action.

---

## 13) Minimal Step Examples

Example: split leaf

- Step 1: action=INSERT_KEY
  explanation="Insert 30 into node N3"
  highlights: node N3, key 30

- Step 2: action=SPLIT_NODE
  explanation="N3 has 5 keys (> 2t-1). Split and promote 30"
  highlights: N3 median key
  isKeyStep=true

- Step 3: action=PROMOTE_KEY
  explanation="Promote 30 to parent N1"
  highlights: parent N1, key slot

- Step 4: action=EDGE_REROUTE
  explanation="Rewire children after split"

---

## 14) Quality Bar Checklist

- Active node/key is always visually obvious.
- Every major structural change has a staged sequence.
- Viewer can pause on key steps and understands why it paused.
- Pseudocode matches the step and highlights correctly.
- No sudden jumps in layout without transition.
- Deep trees remain readable through auto-pan/zoom.

---

## 15) Optional Enhancements

- Minimap with current focus rectangle
- Sound cues for split/merge (subtle)
- Before/after diff toggle
- Export video or step sequence

---

End of document.
