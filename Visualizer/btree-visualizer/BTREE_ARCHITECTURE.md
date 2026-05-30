# B-Tree Visualizer — Complete Architecture Document

> This document specifies every aspect of the B-tree visualizer: visual identity,
> data contracts, node anatomy, animation choreography, narrative system, camera
> behaviour, and module structure. It is written to be implementation-ready —
> a developer should be able to read this and build without guesswork.
>
> **Core mandate:** This is not the linked-list visualizer with a tree bolted on.
> It is a distinct product with its own visual language, its own educational
> personality, and animations designed specifically for the structural drama of
> B-tree operations.

---

## 1. Design Philosophy & Identity

### 1.1 What Makes B-Trees Educationally Unique

B-trees are fundamentally different from linked lists in ways that must shape
every design decision:

- **Nodes hold multiple keys.** A node is not a single value — it is a sorted
  record with 1 to 2t−1 keys and up to 2t children. The slot-level is the unit
  of attention, not the node-level.
- **The tree is two-dimensional.** Layout is not linear. Depth and horizontal
  spread both carry meaning. Camera management is a first-class problem.
- **Operations cascade.** An insert can trigger a split that triggers another
  split all the way to the root. A delete can trigger a borrow or a merge that
  propagates upward. The causal chain is the story — the visualizer must tell it.
- **Invariants are always in tension.** Every step either preserves or
  temporarily violates a B-tree property. The student needs to see which
  property is at stake at every moment.
- **Recursion is the control flow.** The algorithms descend the tree and then
  act on the way back up. The visualizer must make this two-phase structure
  visible.

### 1.2 The Core Educational Bet

The linked-list visualizer's job was to clarify pointer manipulation.
This visualizer's job is different: **it must make the student feel why
a B-tree self-balances.** Not just show that it does, but create the intuition
for why splits propagate upward and why merges pull siblings together. Every
design choice — animation, colour, timing, narration — serves this goal.

### 1.3 What Must Be Distinct From the Linked-List Visualizer

| Dimension | Linked List | B-Tree |
|---|---|---|
| Visual palette | Cold dark navy/slate | Warm deep amber/charcoal |
| Background | Blue-black with blue grid | Near-black with warm brown cast |
| Node shape | Small thin rectangular boxes | Wide "page block" cards with internal slots |
| Unit of attention | Entire node | Individual key slot |
| Layout axis | Horizontal 1D | Vertical tree, levels as rows |
| Camera | Simple pan | Two-level camera: subtree focus + full tree minimap |
| Sidebar identity | Text-heavy explainer | Invariant tracker is the centrepiece |
| Animation character | Smooth tweens | Dramatic staged sequences with weight |
| Typography | Monospace only | Mixed: sans-serif for keys, mono for code |

---

## 2. Visual Identity System

### 2.1 Colour Palette

The palette is warm and architectural. The background reads as a dark amber-brown,
not the cold blue-navy of the linked list. Every colour has a single semantic
responsibility.

```
BACKGROUNDS
  --bg-deep:      #110e09   Canvas background — almost black with warm cast
  --bg-surface:   #1c1710   Node fill (default state) — dark warm brown
  --bg-surface2:  #242018   Sidebar, panels — slightly lighter
  --bg-surface3:  #2d2820   Input fields, chips

BORDERS
  --border:       #3d3425   Subtle dividers
  --border2:      #52472e   Stronger borders, node outlines

TEXT
  --text:         #f0e6d3   Primary text — warm white, not cold white
  --text-muted:   #9c8c6e   Secondary text
  --text-dim:     #5a4e38   Disabled / placeholder

ACCENT (Gold — the active/attention colour)
  --gold:         #d4a843   Primary accent — used for active nodes, highlights
  --gold-light:   #f0c96a   Bright accent — key comparisons, active key slots
  --gold-bg:      #2a2010   Gold background tint

SEMANTIC COLOURS
  --green:        #4ade80   Insert / success
  --green-bg:     #0d2818
  --red:          #f87171   Overflow / error / deletion target
  --red-bg:       #2a0d0d
  --blue:         #60a5fa   Search path / visiting
  --blue-bg:      #0d1a2a
  --purple:       #c084fc   Predecessor/successor / borrow source
  --purple-bg:    #1a0d2a
  --orange:       #fb923c   Underflow warning
  --orange-bg:    #2a1408
```

### 2.2 Typography

Two typefaces. Never substitute one for the other.

```
UI Font:    "Syne" (or "DM Sans" as fallback) — sans-serif, slightly geometric.
            Used for: labels, explanations, sidebar text, scenario names.

Code Font:  "JetBrains Mono" (or "Fira Code") — monospace.
            Used for: key values inside node slots, pseudocode, variable chips,
                      complexity notation, tree property values.
```

Font size scale:
```
  Key value in slot:   20px, weight 700, code font
  Slot label (small):   9px, weight 400, code font, uppercase
  Section title:       10px, weight 700, UI font, uppercase, letter-spacing 0.1em
  Explanation body:    13px, weight 400, UI font, line-height 1.7
  Pseudocode line:     11px, weight 400, code font
  Variable chip:       11px, weight 600, code font
  Badge text:          10px, weight 600, code font
```

### 2.3 Spacing & Sizing Scale

```
  Base unit: 8px

  Sidebar width:         400px (wider than linked list — more content)
  Top bar height:         56px
  Canvas left margin:    5% (tree is centred, not left-aligned)

  Node slot width:        52px
  Node slot height:       56px
  Node slot gap:           4px  (gap between adjacent key slots)
  Node padding-x:         10px  (padding before first slot and after last)
  Node padding-y:          8px
  Node corner radius:     10px
  Node shadow:            0 4px 24px rgba(0,0,0,0.5)

  Level separation:      120px (vertical distance between tree levels)
  Sibling separation:     24px (horizontal gap between sibling nodes)
  Edge width:              1.5px (default), 2.5px (active/highlighted)

  Sidebar section padding: 16px 20px
  Chip padding:            4px 10px
```

### 2.4 Node Anatomy (Pixel-Level Specification)

A B-tree node is a "page block" — a wide rectangular card containing an ordered
row of key slots. This is the most important visual departure from the linked
list's simple boxes.

#### Internal node with 3 keys (t=2, not overflowing):

```
╔═══════════════════════════════════════════════════╗  ← node outline
║                                                   ║     stroke: --border2
║  ┌──────────┐  ┌──────────┐  ┌──────────┐        ║     fill: --bg-surface
║  │          │  │          │  │          │         ║
║  │    20    │  │    35    │  │    52    │         ║  ← key slots
║  │          │  │          │  │          │         ║     each: 52×56px
║  └──────────┘  └──────────┘  └──────────┘        ║     key text: 20px bold
║                                                   ║
╚═══════════════════════════════════════════════════╝
  ↑               ↑               ↑               ↑   ← child pointer dots
  c0              c1              c2              c3      small circles, 6px dia.
  │               │               │               │      connected to edges below
```

Child pointer dots: 6px diameter circles positioned on the bottom edge of the
node, centred between and around the key slots. One dot per child pointer.
Filled with --border2 (default), --gold (active), --blue (search path).

#### Leaf node (same but no pointer dots, different bottom border):

```
╔═══════════════════════════════════════════════════╗
║  ┌──────────┐  ┌──────────┐  ┌──────────┐        ║
║  │    20    │  │    35    │  │    52    │         ║
║  └──────────┘  └──────────┘  └──────────┘        ║
╠═══════════════════════════════════════════════════╣  ← thick bottom border
                                                       (3px solid --gold@0.4)
                                                       signals "leaf level"
```

#### Overflow state (about to split):

```
╔═══════════════════════════════════════════════════╗  ← node outline pulses red
║  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ← 5 slots (2t-1 = 5, full)
║  │  10  │  │  20  │  │  30  │  │  40  │  │  50  │  ← median slot (index 2)
║  └──────┘  └──────┘  └──────┘  └──────┘  └──────┘    has gold outline, glow
╠═══════════════════════════════════════════════════╣
  "OVERFLOW — 5 keys > 2t-1 = 5... split required"       ← inline label beneath
```

Wait — 2t-1 with t=3 means 5 keys is exactly full. Overflow would be at 6 keys
(during the insert step, before the split). The overflow state shows the node
momentarily at 6 keys (exceeding 2t-1=5) outlined in red before the split fires.

#### Node badges:

Root badge: Small pill above the node — "root" in --gold text on --gold-bg.
Positioned centered above the node's top edge, 4px gap.

Leaf badge: Small pill to the right — "leaf" in --text-muted on --bg-surface3.

Underflow badge: Small pill in --orange above the node — "underflow (1 < t-1=2)".
Appears when a node has fewer than t-1 keys (post-deletion, before fix).

### 2.5 Edge Design

Edges connect child pointer dots to the top-centre of child nodes.

```
  Default:  straight line, 1.5px, color --border2, opacity 0.6
  Active:   2.5px, color --gold, opacity 1.0 (the path being descended)
  New:      animated dash-draw in --green
  Removed:  animated fade + shorten in --red
```

Edges are not arrows. Direction is implied by the tree structure (always
parent → child). Adding arrowheads would create visual clutter. The child
pointer dots on the parent node make the source of each edge clear.

---

## 3. Data Model

### 3.1 B-Tree State Schema

A complete, immutable snapshot of the tree at one moment in time. Every Step
carries one. Stored as a plain serialisable object (no classes, no methods).

```js
{
  t:      number,          // minimum degree — defines all size constraints
  rootId: string,          // ID of the root node
  nodes:  {                // all nodes keyed by ID
    [nodeId: string]: {
      id:       string,
      keys:     number[],  // sorted ascending, length in [t-1, 2t-1]
                           // (root may have as few as 1 key)
      children: string[],  // child node IDs, length = keys.length + 1
                           // empty array for leaf nodes
      isLeaf:   boolean,
      parentId: string | null,  // denormalised for O(1) parent lookup
    }
  }
}
```

Derived values (computed on demand, never stored):
```
  height(state)      = length of path from root to any leaf
  nodeCount(state)   = Object.keys(state.nodes).length
  keyCount(state)    = sum of node.keys.length for all nodes
  isOverflow(node)   = node.keys.length > 2t - 1
  isUnderflow(node)  = node.keys.length < t - 1 AND node is not root
```

### 3.2 Step Schema

Every algorithm step emits one Step object. This is the contract between
the algorithm layer and both the animation and narrative layers.

```js
{
  // Identification
  stepIndex:      number,       // position in the step array (0-based)
  action:         string,       // ACTION constant (see 3.3)
  isKeyStep:      boolean,      // true = conceptually important pause

  // State
  state:          BTreeState,   // deep-cloned snapshot — never shared between steps

  // Highlights (what the animation layer should visually emphasise)
  highlights: {
    nodes: [{ nodeId: string, role: NODE_ROLE }],
    keys:  [{ nodeId: string, keyIndex: number, role: KEY_ROLE }],
    edges: [{ fromId: string, toId: string, role: EDGE_ROLE }],
  },

  // Narrative data
  explanation:    string,       // 1–3 sentence explanation of why this step happens
  pseudocodeLine: number | null,// active line index in the current operation's pseudocode
  variables: {                  // named values for the variable inspector
    node?:        string,       // current node ID
    parent?:      string,       // parent node ID
    key?:         number,       // the key being operated on
    keyIndex?:    number,       // key's index within its node
    t?:           number,       // minimum degree
    leftSibling?: string,       // left sibling node ID
    rightSibling?:string,       // right sibling node ID
    childIndex?:  number,       // which child pointer we descended through
    medianIndex?: number,       // median key index during split
    predecessor?: number,       // predecessor key value during delete
  },

  // Meta — extra context for choreography and narrative decisions
  meta: {
    phase?:      'descend' | 'act' | 'unwind', // which phase of the recursive algorithm
    reason?:     'overflow' | 'underflow' | 'rotate' | 'merge' | 'found' | 'not-found',
    splitFrom?:  string,    // nodeId that was split (for SPLIT_NODE step)
    mergeLeft?:  string,    // left node in a merge
    mergeRight?: string,    // right node in a merge
    depth?:      number,    // current recursion depth (0 = root level)
  }
}
```

### 3.3 Action Constants

```js
// ── General ──────────────────────────────────────────────────────────────────
INITIAL_STATE         // before any operation starts
OPERATION_COMPLETE    // final state after operation completes

// ── Search ───────────────────────────────────────────────────────────────────
SEARCH_ENTER_NODE     // arriving at a node during search/insert descent
SEARCH_COMPARE_KEY    // comparing target key against one key in the current node
SEARCH_GO_LEFT        // key < current key, descend into left subtree
SEARCH_GO_RIGHT       // key > current key, continue comparing rightward
SEARCH_DESCEND        // decided which child to follow, now descending
SEARCH_FOUND          // key found at a specific slot
SEARCH_NOT_FOUND      // reached a leaf without finding key

// ── Insert ───────────────────────────────────────────────────────────────────
INSERT_INTO_LEAF      // placing a key into a leaf node (sorted position)
INSERT_SHIFT_KEYS     // existing keys shifting right to make room
OVERFLOW_DETECTED     // node now has 2t keys — split required
SPLIT_PREPARE         // highlighting the median key before split
SPLIT_EXECUTE         // node tears apart into left + right halves
PROMOTE_KEY           // median key rising to parent
PROMOTE_INTO_PARENT   // parent absorbs the promoted key
SPLIT_ROOT            // special case: root split creates a new root
EDGE_REROUTE          // child pointers rewired after split

// ── Delete ───────────────────────────────────────────────────────────────────
DELETE_FIND_KEY       // arriving at the node containing the key to delete
DELETE_FROM_LEAF      // removing a key directly from a leaf
DELETE_SHIFT_KEYS     // remaining keys shift left to close the gap
FIND_PREDECESSOR      // descending to find in-order predecessor
REPLACE_WITH_PRED     // replacing deleted key with its predecessor value
UNDERFLOW_DETECTED    // node now has t-2 keys — fix required
FIX_CHOOSE_STRATEGY   // deciding: borrow-left, borrow-right, or merge
BORROW_LEFT_PREPARE   // highlighting: left sibling + parent separator
BORROW_LEFT_ROTATE    // key rotates: sibling → parent → current node
BORROW_RIGHT_PREPARE  // highlighting: right sibling + parent separator
BORROW_RIGHT_ROTATE   // key rotates: sibling → parent → current node
MERGE_PREPARE         // highlighting two nodes + separator key to merge
MERGE_PULL_SEPARATOR  // separator key descends from parent into left node
MERGE_ABSORB_KEYS     // right node's keys move into left node
MERGE_ABSORB_CHILDREN // right node's children re-homed to left node
MERGE_REMOVE_NODE     // right node shell disappears
MERGE_UPDATE_PARENT   // parent loses separator + right-child pointer
ROOT_SHRINK           // root emptied — its only child becomes new root
```

### 3.4 Highlight Role Constants

```js
// Node roles
NODE_ROLES = {
  DEFAULT:       'default',
  ACTIVE:        'active',       // node currently being visited (gold)
  PARENT:        'parent',       // parent of the active node (dimly gold)
  SPLIT_LEFT:    'split_left',   // left half of a split (green)
  SPLIT_RIGHT:   'split_right',  // right half of a split (green)
  MERGE_TARGET:  'merge_target', // node receiving merged keys (blue)
  MERGE_SOURCE:  'merge_source', // node being absorbed (red)
  SIBLING_LEFT:  'sibling_left', // left sibling in borrow operation (purple)
  SIBLING_RIGHT: 'sibling_right',// right sibling in borrow operation (purple)
  OVERFLOW:      'overflow',     // node exceeding 2t-1 keys (red pulse)
  UNDERFLOW:     'underflow',    // node with < t-1 keys (orange pulse)
  DIM:           'dim',          // not involved in current step (30% opacity)
}

// Key slot roles
KEY_ROLES = {
  DEFAULT:    'default',
  COMPARING:  'comparing',  // currently being compared against target
  FOUND:      'found',      // target key located here
  INSERTING:  'inserting',  // key being placed here
  DELETING:   'deleting',   // key being removed
  MEDIAN:     'median',     // median key in a split
  PROMOTING:  'promoting',  // key rising to parent
  SEPARATOR:  'separator',  // parent key separating two siblings (merge/borrow)
  PREDECESSOR:'predecessor',// predecessor key in delete operation
}

// Edge roles
EDGE_ROLES = {
  DEFAULT:    'default',
  PATH:       'path',       // edge on the descent path
  NEW:        'new',        // newly created edge
  REMOVING:   'removing',   // edge being severed
  REROUTING:  'rerouting',  // edge changing target
}
```

---

## 4. Layout Engine

### 4.1 Design Contract

The layout engine is a pure function. It never mutates state, never touches the
DOM, and never imports from any other module. It is testable in isolation.

```js
computeLayout(state, theme) → LayoutMap

LayoutMap = {
  nodes: {
    [nodeId]: {
      x:      number,  // centre-x of the node
      y:      number,  // top-y of the node
      width:  number,  // computed from key count
      height: number,
    }
  },
  keys: {
    [nodeId]: [
      { x: number, y: number, width: number, height: number }  // per key slot
    ]
  },
  pointerDots: {
    [nodeId]: [
      { x: number, y: number }  // per child pointer dot, bottom edge of node
    ]
  },
  edges: {
    [`${fromId}→${childIndex}`]: {
      fromDot: { x: number, y: number },  // child pointer dot position
      toNode:  { x: number, y: number },  // top-centre of child node
      path:    string,                    // SVG path string
    }
  }
}
```

### 4.2 Node Width Formula

Node width is dynamic — it grows with the number of keys:

```
nodeWidth(node) = (node.keys.length × SLOT_WIDTH)
                + ((node.keys.length - 1) × SLOT_GAP)
                + (2 × NODE_PADDING_X)

where:
  SLOT_WIDTH    = 52px
  SLOT_GAP      = 4px
  NODE_PADDING_X = 10px

Examples:
  1 key:  52 + 0 + 20 = 72px
  3 keys: 156 + 8 + 20 = 184px
  5 keys: 260 + 16 + 20 = 296px  (maximum for t=3)
```

### 4.3 Tree Layout Algorithm

Use a modified **Reingold-Tilford** algorithm adapted for variable-width nodes:

**Phase 1 — Assign x to leaves:**
Space leaf nodes at their natural widths with SIBLING_SEPARATION gaps.
Centre the leftmost leaf at x=0. Leaves are positioned left-to-right in
in-order traversal order.

**Phase 2 — Assign x to internal nodes:**
Each internal node is centred over its leftmost and rightmost child:
```
  node.x = (leftmostChild.x + rightmostChild.x) / 2
```
If the node is wider than its subtree span, its children are shifted outward.

**Phase 3 — Assign y by level:**
```
  node.y = depth(node) × (NODE_HEIGHT + LEVEL_SEPARATION)
  
  where NODE_HEIGHT = NODE_PADDING_Y×2 + SLOT_HEIGHT = 8 + 56 + 8 = 72px
        LEVEL_SEPARATION = 120px
```

**Phase 4 — Centre the whole tree:**
After computing all positions, find the total tree bounds and translate
everything so the tree is horizontally centred at x=0. The SVG viewport
applies a zoom transform to centre x=0, y=0 in the canvas.

**Phase 5 — Compute slot positions:**
For each node, compute the x, y of each key slot relative to the node's
top-left corner:
```
  slot[i].x = NODE_PADDING_X + i × (SLOT_WIDTH + SLOT_GAP)
  slot[i].y = NODE_PADDING_Y
```

**Phase 6 — Compute pointer dot positions:**
```
  dot[i].x = NODE_PADDING_X + (i × (SLOT_WIDTH + SLOT_GAP)) - (SLOT_GAP/2)
  dot[i].y = node.height  (bottom edge)
  
  — one dot before the first slot (i=0)
  — one dot after each slot (i=1..n)
```

### 4.4 Layout Stability

When the tree changes (split, merge, borrow), nodes move to new positions.
The layout engine always computes the target layout. The animation layer is
responsible for tweening nodes from their previous positions to their new ones.

To support this, the layout engine preserves node IDs. When a split creates
two new nodes, the left half keeps the original node's ID. Only the right
half gets a new ID. This minimises unnecessary enter/exit transitions.

---

## 5. Operations — Algorithm & Step Sequences

Every operation is a pure function:
```js
search(state, key)         → Step[]
insert(state, key)         → Step[]
delete(state, key)         → Step[]
```

These functions do not modify `state`. They produce a new state snapshot for
each step, deep-cloned. The original state is never mutated.

### 5.1 Search

**Pseudocode (indexed for pseudocodeLine):**
```
0:  function search(node, key):
1:    for i = 0 to node.keys.length - 1:
2:      if key == node.keys[i]:
3:        return (node, i)       // FOUND
4:      if key < node.keys[i]:
5:        if node.isLeaf: return NOT_FOUND
6:        return search(node.children[i], key)
7:    if node.isLeaf: return NOT_FOUND
8:    return search(node.children[node.keys.length], key)
```

**Step sequence for search(key=38) in a tree with root=[20,50], left=[10,15],
middle=[25,35,38,45], right=[60,70]:**

1. `INITIAL_STATE` — show full tree, no highlights. Explanation: introduce the search target and the search strategy (key comparison at each node, descend to child).

2. `SEARCH_ENTER_NODE` — highlight root. Explanation: "We begin at the root. Every search starts here, regardless of tree depth."

3. `SEARCH_COMPARE_KEY` (keyIndex=0, key=20) — highlight root slot 0. Explanation: "Is 38 == 20? No. Is 38 < 20? No — 38 is greater, so we continue rightward."

4. `SEARCH_GO_RIGHT` — move highlight to slot 1. Explanation: "38 > 20, so we skip the left subtree entirely. Any key in that subtree is ≤ 20."

5. `SEARCH_COMPARE_KEY` (keyIndex=1, key=50) — highlight root slot 1. Explanation: "Is 38 == 50? No. Is 38 < 50? Yes — 38 must be in the subtree between 20 and 50."

6. `SEARCH_DESCEND` — highlight edge from root's child-pointer-2 to middle node. Explanation: "We descend through child pointer 1 (between keys 20 and 50). 20 < 38 < 50 must be satisfied by every key in this subtree."

7. `SEARCH_ENTER_NODE` — highlight middle node. Explanation: "We are now at depth 1. This node is a leaf."

8. `SEARCH_COMPARE_KEY` (keyIndex=0, key=25) — Explanation: "Is 38 == 25? No. Is 38 < 25? No."

9. `SEARCH_COMPARE_KEY` (keyIndex=1, key=35) — Explanation: "Is 38 == 35? No. Is 38 < 35? No."

10. `SEARCH_COMPARE_KEY` (keyIndex=2, key=38) — highlight slot green. Explanation: "Is 38 == 38? YES — found!"

11. `SEARCH_FOUND` — highlight slot (found role). isKeyStep=true. Explanation: "Search complete. Key 38 found at depth 1, index 2. Search required 3 comparisons across 2 nodes."

### 5.2 Insert

Insert uses **proactive splitting** (split on the way down, before overflow).
This avoids a second pass upward.

**Pseudocode:**
```
0:  function insert(key):
1:    if root is full (2t-1 keys):
2:      newRoot = createNode()
3:      newRoot.children = [root]
4:      splitChild(newRoot, 0, root)
5:      root = newRoot
6:    insertNonFull(root, key)
7:
8:  function insertNonFull(node, key):
9:    i = node.keys.length - 1
10:   if node.isLeaf:
11:     shift keys right to insert in sorted position
12:     node.keys.insert(key at correct position)
13:   else:
14:     find i such that key > node.keys[i]
15:     if node.children[i+1] is full:
16:       splitChild(node, i+1, node.children[i+1])
17:       if key > node.keys[i+1]: i++
18:     insertNonFull(node.children[i+1], key)
19:
20: function splitChild(parent, i, child):
21:   newNode = createNode()
22:   medianKey = child.keys[t-1]
23:   newNode.keys = child.keys[t:]
24:   child.keys = child.keys[:t-1]
25:   if not child.isLeaf:
26:     newNode.children = child.children[t:]
27:     child.children = child.children[:t]
28:   parent.keys.insert(medianKey at position i)
29:   parent.children.insert(newNode at position i+1)
```

**Step-by-step for a split:**

When a full child is encountered during descent, the split fires *before*
descending. Steps emitted:

1. `OVERFLOW_DETECTED` — highlight the full node. isKeyStep=true. Explanation: "This node has 2t-1=5 keys. Before descending, we must split it preemptively. B-trees split on the way down so we never need to backtrack."

2. `SPLIT_PREPARE` — highlight median key slot. Explanation: "The median key (index t-1=2, value: 30) will be promoted. Keys to its left stay in this node; keys to its right move to a new sibling."

3. `SPLIT_EXECUTE` — the node tears apart. isKeyStep=true. Two new node shells appear, left keys in the left shell, right keys in the right shell. The median key is shown "floating" between them. Explanation: "Split: left node keeps keys [10,20]. Right node gets keys [40,50]. The median 30 will rise to the parent."

4. `PROMOTE_KEY` — the median key animates upward along an arc to its slot in the parent. isKeyStep=true. Explanation: "Key 30 is promoted to the parent node. It will separate the two new siblings in the parent's key array."

5. `PROMOTE_INTO_PARENT` — parent node momentarily highlighted, the new key slides into its sorted position, existing keys shift right. Explanation: "Parent absorbs key 30 at index 1. Two new child pointers are wired: left child (≤30) and right child (>30)."

6. `EDGE_REROUTE` — edges from parent to the two new children animate into place. Explanation: "Child pointers updated. The split is complete. We now descend into the correct child."

**Root split (special case):**

When the root itself is full, a new root must be created.

1. `OVERFLOW_DETECTED` on root — Explanation: "The root is full (2t-1 keys). Root splits are special: we create a new root above the current one. This is the only way a B-tree grows in height."

2. `SPLIT_ROOT` — new root shell appears above the current root. Median key animates upward into the new root. isKeyStep=true. Explanation: "New root created with 1 key (the median). This increases the tree height by 1. Note: all leaves remain at the same depth — the tree is still perfectly balanced."

3. Continue split steps as above.

### 5.3 Delete

Delete is the most complex operation. Three cases must be handled:

**Case 1: Key is in a leaf node.**
- If leaf has > t-1 keys: delete directly.
- If leaf has exactly t-1 keys: need to fix (borrow or merge) first.

**Case 2: Key is in an internal node.**
- Replace with in-order predecessor (or successor).
- Then delete the predecessor from the leaf.

**Case 3: Key not in current node.**
- Descend. Ensure the child we descend into has > t-1 keys (fix if needed).

**Step sequence for Borrow Left:**

When the current node underflows and its left sibling can spare a key:

1. `UNDERFLOW_DETECTED` — highlight current node. Explanation: "After deletion, this node has t-2 keys, below the minimum t-1=2. We must fix this before returning."

2. `FIX_CHOOSE_STRATEGY` — highlight left sibling. Explanation: "Left sibling has 3 keys > t-1=2. It can spare one. We will rotate: move its rightmost key up to the parent, and bring the parent separator down to us."

3. `BORROW_LEFT_PREPARE` — highlight left sibling, parent separator key, and current node simultaneously. isKeyStep=true. Explanation: "Three elements will move in sequence: (1) sibling's rightmost key rises to parent, (2) parent's separator descends to current node, (3) if sibling has children, its rightmost child is re-homed."

4. `BORROW_LEFT_ROTATE` — keys animate in a triangular arc: sibling's rightmost key travels up to the parent's separator slot; the parent's separator slides down-right into the current node's leftmost slot. isKeyStep=true. Explanation: "Rotation complete. The parent separator (25) is now in our node. Sibling's key (20) is now the new separator. Order is preserved."

5. `EDGE_REROUTE` (if internal node) — sibling's rightmost child moves to current node's leftmost child position. Explanation: "The sibling's rightmost subtree is re-assigned to our leftmost child pointer. It contains keys in (new-separator, old-separator) range — which is now ours."

**Step sequence for Merge:**

When neither sibling can spare a key:

1. `UNDERFLOW_DETECTED` — Explanation: "Node underflows and neither sibling can spare a key (both have exactly t-1=2 keys). We must merge."

2. `FIX_CHOOSE_STRATEGY` — highlight both siblings and the parent separator. Explanation: "We will merge the current node with its left sibling. The parent separator key descends to join them, and the parent loses one key."

3. `MERGE_PREPARE` — highlight both nodes + separator. isKeyStep=true. Explanation: "Merge: left node (keys: [10, 20]) + separator from parent (25) + right node (keys: [30]) → merged node [10, 20, 25, 30]. This is exactly 2(t-1)+1 = 2t-1 keys — exactly full."

4. `MERGE_PULL_SEPARATOR` — parent separator key animates downward into the left node. Explanation: "Separator descends: 25 joins the left node."

5. `MERGE_ABSORB_KEYS` — right node's keys animate leftward into the left node, one by one. isKeyStep=true. Explanation: "Right node's keys migrate left."

6. `MERGE_ABSORB_CHILDREN` (if internal) — right node's children are re-assigned. Explanation: "Right node's children are re-homed to the merged node."

7. `MERGE_REMOVE_NODE` — right node shell dissolves. isKeyStep=true. Explanation: "Right node removed. It no longer exists."

8. `MERGE_UPDATE_PARENT` — parent loses the separator key and right child pointer. If parent is root and now empty: `ROOT_SHRINK`. Explanation: "Parent loses one key and one child pointer. If the parent now underflows, the fix propagates upward — this is the recursive nature of B-tree deletion."

---

## 6. Animation System

### 6.1 Renderer

- **SVG** as the rendering target, driven by **D3**.
- Three SVG layers in z-order (bottom to top):
  1. `layer-edges` — all edge paths
  2. `layer-nodes` — all node shapes, slots, labels
  3. `layer-floats` — keys in flight during split/merge/borrow animations,
                       badges, camera focus rings
- D3 keyed data joins on stable IDs for smooth transitions.
- All transitions use D3's `transition().delay().duration()` chain.
- The D3 `easing` used throughout: `d3.easeCubicInOut` for moves,
  `d3.easeBackOut` for elements entering (slight overshoot = satisfying),
  `d3.easeCubicIn` for elements exiting (accelerate out).

### 6.2 Per-Operation Choreography Specifications

Each action constant maps to a timing plan. Times in milliseconds.

#### INSERT_INTO_LEAF

```
t=0ms:   Highlight the target leaf node (gold outline, 200ms)
t=200ms: The new key's slot appears — slides in from slightly above,
          opacity 0→1, scale 0.7→1, duration 300ms, ease easeBackOut
t=350ms: Existing keys to the right of the insertion point shift rightward,
          staggered by 40ms per key, duration 250ms each
t=0ms:   (simultaneously) slot background flashes green then fades to normal (500ms)
```

#### SPLIT_EXECUTE (the centrepiece animation — must feel dramatic)

```
t=0ms:    Node outline turns red and pulses (2 cycles, 400ms total)
t=300ms:  A crack line appears vertically through the median slot (50ms, white)
t=350ms:  Left half slides left (200px over 500ms, ease easeInOut)
          Right half slides right (200px over 500ms, ease easeInOut)
          Both halves maintain their original y position during this
t=350ms:  Median key slot scales up (1.0→1.2, 150ms) then begins floating upward
t=500ms:  Median key animates along a smooth arc path toward its parent slot
          Arc apex is 80px above the midpoint. Duration 600ms, ease easeInOut.
t=850ms:  Left and right halves animate down to their final layout positions
          (computed by the layout engine). Duration 500ms.
t=850ms:  New edges from parent to both halves draw in (dash-draw animation,
          left to right, 300ms each, staggered by 100ms)
```

#### PROMOTE_INTO_PARENT

```
t=0ms:   Parent node highlighted (gold, 200ms)
t=150ms: Parent node width expands smoothly to accommodate new key (300ms)
t=200ms: Existing parent keys to the right of insertion point slide right (200ms)
t=300ms: Promoted key arrives in its slot (scale 1.2→1.0, green flash, 250ms)
t=400ms: New child pointer dot appears on parent's bottom edge (fade in, 200ms)
```

#### BORROW_LEFT_ROTATE (the "tumble" animation)

```
The key rotation is the most visually distinctive animation in the borrow op.
The three keys involved (sibling's rightmost, parent separator, slot in current
node) trace a triangular path.

t=0ms:   Sibling's rightmost key slot highlights purple (200ms)
t=150ms: Parent separator highlights gold (200ms)
t=300ms: Clone of sibling's key begins arc animation:
          - Leaves sibling slot with a slight scale-up (1.0→1.1)
          - Travels up-right along a cubic bezier to the parent separator slot
          - Duration 500ms, ease easeInOut
          Simultaneously, parent separator key begins arc animation:
          - Leaves parent slot, travels down-left to current node's leftmost slot
          - Duration 500ms (same timing, parallel)
          - Ease easeInOut
t=600ms: Both keys land simultaneously. sibling shrinks by one slot (right-to-left
          contraction, 200ms). Current node grows by one slot (200ms).
t=700ms: (if internal) Sibling's rightmost child edge animates to current node's
          leftmost child position (200ms).
```

#### MERGE_EXECUTE (gravity-pull animation)

```
t=0ms:   Both sibling nodes and parent separator highlight (200ms)
t=200ms: isKeyStep pause — let student read the situation
t=0ms:   (after resume) Separator key in parent begins falling downward
          into the left node, arc path, 400ms
t=300ms: Right node's keys begin peeling off and flying leftward into the
          left node, staggered by 80ms per key, each 350ms duration
          Keys enter their destination slots with a slight bounce (easeBackOut)
t=600ms: Right node's children edges reroute to the merged node (if internal)
t=700ms: Right node shell contracts (scale 1.0→0.0, opacity 1→0), 300ms
t=800ms: Parent loses separator: remaining parent keys slide together (200ms)
          Parent loses right child pointer dot (fade, 150ms)
t=900ms: If parent underflows, it highlights orange and a small badge appears:
          "Underflow — propagating fix upward"
```

#### ROOT_SHRINK

```
t=0ms:   Root (now empty) highlights red, pulsing
t=300ms: The single remaining child begins rising upward toward the root position
          (moves up by one full level). Duration 600ms, ease easeInOut.
t=500ms: Old root shell fades and contracts simultaneously
t=700ms: New root badge appears on the promoted child
t=800ms: All other nodes shift upward by one level (the tree loses one level of
          height). Duration 500ms, staggered from top to bottom.
t=900ms: A banner appears briefly: "Tree height decreased from N to N-1.
          All leaves are still at the same depth."
```

### 6.3 Focus System

The focus system creates a "spotlight" effect — non-relevant parts of the tree
dim during complex operations to direct attention.

**Focus rules by operation phase:**

| Phase | Focused elements | Dimmed elements |
|---|---|---|
| Search descent | Current node + path from root | All off-path nodes |
| Pre-split | Overflowing node + its parent | All others |
| Split | Left node, right node, parent | Everything else |
| Borrow | Current node + sibling + parent separator | Everything else |
| Merge | Both merged nodes + parent | Everything else |
| After operation | Entire tree (full brightness restored) | — |

Dimming: non-focused nodes transition to `opacity: 0.25` over 300ms.
Restoring: `opacity: 1.0` over 400ms.

This is implemented in a dedicated `FocusController` module (see Section 8).

### 6.4 Transition Choreographer Module

```js
// Input: prevStep, currentStep, theme timings
// Output: a ChoreographyPlan object

ChoreographyPlan = {
  nodeEnter:      { delay, duration },
  nodeExit:       { delay, duration },
  nodeMove:       { delay, duration },
  nodeResize:     { delay, duration },  // width change when keys are added/removed
  keyEnter:       { delay, duration },
  keyExit:        { delay, duration },
  keyMove:        { delay, duration },  // key flying through space (float layer)
  edgeEnter:      { delay, duration },
  edgeExit:       { delay, duration },
  edgeReroute:    { delay, duration },
  highlightFade:  { delay, duration },
  focusChange:    { delay, duration },
  cameraPan:      { delay, duration },
}
```

The choreographer is the only place where timing constants live. No hardcoded
delays anywhere else in the animation layer.

---

## 7. Camera System

The camera system is independent of the layout engine. It owns the SVG zoom
transform and decides *where* to look based on the current step.

### 7.1 Two-Level Camera Architecture

**Level 1 — Subtree Focus Camera:**
Manages the main SVG viewport. Pans and zooms to keep the active region visible
and appropriately sized. This is the camera that animates during an operation.

**Level 2 — Minimap:**
A fixed-size inset (bottom-right of canvas, 200×150px) showing the entire tree
at a reduced scale. A translucent rectangle shows the current viewport. The
student can click the minimap to teleport the main camera.

### 7.2 Camera Behaviour Rules

```
Rule 1 — Descent: As the algorithm descends level by level, the camera
  follows — panning down and slightly zooming in to keep the active node
  large. Pan speed: 400ms per level.

Rule 2 — Split: Before the split animation, zoom out enough to show both
  the overflowing node AND its parent in frame simultaneously. This is
  important because the student needs to see where the median goes.
  Zoom out takes 400ms.

Rule 3 — Merge: Before the merge animation, zoom out to show both siblings
  AND the parent separator in frame. Same rule as split.

Rule 4 — Root split: Zoom out to show the entire tree before the new root
  is created. The student needs to see the height change in context.

Rule 5 — Operation complete: After the last step, zoom to fit the entire
  final tree in frame, with 5% padding on all sides. Duration 600ms.

Rule 6 — Cascade: If a merge/split propagates upward to the parent,
  the camera smoothly rises one level (pan upward, 400ms) to follow.
```

### 7.3 Camera Transitions

Camera transitions are always smooth cubic-bezier curves. Never instant jumps.
The D3 zoom transform is tweened with `d3.zoom().transform()`.

When the camera needs to pan AND zoom simultaneously, both transforms are
animated on the same transition chain so they complete together.

### 7.4 Minimap Module

```
Position:    Bottom-right of canvas, absolute positioning
Size:        200px × 150px
Background:  --bg-surface with 80% opacity, border --border
Scale:       Always fits the full tree
Viewport:    Semi-transparent --gold rectangle showing main camera view
Interaction: Click to teleport (500ms animated pan in main camera)
Update:      Redraws on every frame (lightweight — just node rectangles,
              no slot detail, no text)
```

---

## 8. Narrative System

The narrative layer owns five components, each receiving its own DOM element.

### 8.1 InvariantTracker (New — not in linked list)

This is the centrepiece of the B-tree narrative — the component that has no
equivalent in the linked list visualizer. It is always visible and always
up to date.

**Layout:**
```
┌─────────────────────────────────────────┐
│  B-TREE PROPERTIES                      │
│─────────────────────────────────────────│
│  t (min degree)          3              │
│  Max keys / node         5  (2t-1)      │
│  Min keys / node         2  (t-1)       │
│─────────────────────────────────────────│
│  CURRENT STATE                          │
│  Tree height             3              │
│  Total nodes             9              │
│  Total keys              22             │
│─────────────────────────────────────────│
│  ACTIVE NODE STATUS                     │
│  Node N4: 5 keys   ████████░░  [FULL]  │
│  Node N2: 1 key    ██░░░░░░░░  [UNDER] │
└─────────────────────────────────────────┘
```

The "Active Node Status" section updates every step. It shows a
mini progress bar for the active node's key count against min/max thresholds.

**Colour coding:**
- Key count at min (t-1): orange bar, "UNDERFLOW" badge
- Key count in safe range: green bar
- Key count at max (2t-1): amber bar, "FULL" badge
- Key count exceeding max (during overflow step): red bar, "OVERFLOW" badge

**Update behaviour:** The InvariantTracker updates on every step, but the
"Active Node Status" section cross-fades only when the active node changes
(not on every comparison step, which would be distracting).

### 8.2 RecursionDepthIndicator (New — not in linked list)

B-tree algorithms are recursive. This component makes the call stack visible.

**Layout** — a breadcrumb trail below the top bar or within the sidebar:
```
  Root [N1] → N3 → N7 (current, depth 2)
```

Each breadcrumb shows the node ID and (on hover) its key contents. The current
node is highlighted. When the recursion unwinds (fix propagates upward), the
breadcrumb shrinks rightward — visually showing the unwinding.

**Transitions:** Each new level added (descent) animates from right, fading in.
Each level removed (unwind) fades out to the right.

### 8.3 ExplanationPanel

Enhanced from the linked list version with two structural differences:

**Two-part explanation structure:**
- **What** (larger, 14px): "Node N7 overflowed — 6 keys exceeds 2t-1=5."
- **Why** (smaller, 12px, muted): "B-trees allow at most 2t-1 keys per node to ensure efficient O(log n) operations. Overflow means a node is too full and must split."

The "Why" part is always present for `isKeyStep=true` steps. For non-key steps
it may be omitted to keep the panel lightweight.

**Rich text tokens** (same as linked list but extended):
- Property expressions like `2t-1=5`: styled as a math expression (gold)
- Node IDs like `N4`: styled as a code chip (blue)
- Key values: styled in a distinct colour (pink/rose)
- Structural terms ("leaf", "root", "parent", "sibling"): slightly bold

### 8.4 PseudocodePanel

Enhanced with one new feature: **phase annotation**.

Above the pseudocode block, a small label shows which phase of the algorithm
is currently active:
```
  [PHASE: DESCEND ↓]    — when going down the tree
  [PHASE: SPLIT ↷]      — when splitting
  [PHASE: FIX ↑]        — when fixing underflow on the way up
```

This helps students understand the two-phase (down then up) nature of the
delete algorithm specifically.

Syntax highlighting tokens: same as linked list visualizer.

### 8.5 VariableInspector

Same architecture as the linked list visualizer, but with B-tree-specific
variable roles:

```
  node:         blue    — current node being examined
  parent:       gold    — parent of the current node
  key:          rose    — the key value being operated on
  leftSibling:  purple  — left sibling (borrow/merge context)
  rightSibling: purple  — right sibling (borrow/merge context)
  medianIndex:  amber   — median index during split
  predecessor:  teal    — predecessor key during delete
  t:            dim     — minimum degree (changes rarely)
```

**Node ID resolution:** Variable values that are node IDs (node, parent,
leftSibling, rightSibling) display as the node's key array, not the raw ID:
```
  node = N4 → displays as "node = [20, 35, 50]"
```
This is more useful than seeing "n4" since it immediately shows what's in
the node.

### 8.6 ComplexityPanel

Extended with per-operation notes about which case is currently running:

```
  Operation: Delete
  ──────────────────
  Time:   O(t · log_t(n))
  Space:  O(h)  [recursion stack]
  ──────────────────
  Current case: Fix underflow (borrow-left)
  Worst case:   O(h) merge cascade to root
```

The "Current case" line updates per step based on `step.meta.reason`.

---

## 9. UI Shell

### 9.1 Layout

```
┌─────────────────────────────────────────────────────────────┐
│  TOPBAR                                                      │
│  [logo] [op selector] [key input] [t selector] [▶ Run]      │
│         [scenario: ▼]                          [status ●]   │
├────────────────────────────────────┬────────────────────────┤
│                                    │  SIDEBAR               │
│  CANVAS (SVG)                      │  [InvariantTracker]    │
│                                    │  [RecursionDepth]      │
│           tree renders here        │  [Pseudocode]          │
│                                    │  [Explanation]         │
│                     [minimap]      │  [VariableInspector]   │
│  ┌──────────────────────────────┐  │  [Complexity]          │
│  │  PLAYBACK CONTROLS           │  │  [Legend]              │
│  └──────────────────────────────┘  │                        │
└────────────────────────────────────┴────────────────────────┘
```

Sidebar width: 400px (wider than the linked-list sidebar — more content).
Canvas: remaining width.

### 9.2 Top Bar Components

**Logo:** `btree.viz` — warm gold on dark background. Different wordmark from
the linked list (`list.viz`).

**Operation selector:** Dropdown with groups:
```
  ─── Core ───
  Search(key)
  Insert(key)
  Delete(key)
  ─── Inspect ───
  Validate tree (checks all invariants, shows results)
```

**Key input:** Number field, range 1–9999.

**t selector:** Number field or small stepper, range 2–5.
Below the stepper, always show: "Max keys: 2t-1 = N" (updates live as t changes).

**Scenario dropdown:** Pre-built scenario selector (see Section 10).

**Run button:** Warm gold background, white text. On click: validates inputs,
generates steps, passes to playback controller.

### 9.3 Playback Controls

Identical function to the linked list visualizer, but visually distinct:
- Warm amber accent for the progress fill
- Different button icon style (slightly more rounded)
- The progress bar shows key-step markers as small gold ticks at the positions
  where `isKeyStep=true`. Students can see at a glance where the important
  moments are before playing.

### 9.4 Key-Step Banner

A banner appears at the top of the canvas when the controller auto-pauses on
a key step. Unlike the linked list, the banner shows the specific reason:
```
  ⚑ Overflow — split required
  ⚑ Underflow — fix required
  ⚑ Split propagating upward
  ⚑ Tree height increased
  ⚑ Key found
```

The reason comes from `step.meta.reason`.

---

## 10. Scenario Mode

### 10.1 Scenario Schema

```js
{
  id:          string,
  name:        string,
  description: string,   // 1–2 sentence hook shown before play
  t:           number,
  initialKeys: number[], // keys to pre-populate before the scenario runs
  operations: [
    { op: 'insert' | 'delete' | 'search', key: number }
  ],
  pauseBetweenOps: number  // ms pause between sequential operations
}
```

### 10.2 Built-In Scenarios

**"Database Index Builder"**
> "Watch a B-tree build itself as 15 records are indexed one by one. Notice how
> splits propagate upward and the tree grows in height."
- t=3, insert keys: [10, 20, 5, 6, 12, 30, 7, 17, 3, 25, 8, 50, 45, 35, 40]
- Chosen to trigger multiple splits and one root split.

**"Split Cascade"**
> "A worst-case insertion sequence that triggers a chain of splits all the way
> to the root, increasing tree height."
- t=2, insert until every node is full, then insert one more.
- Demonstrates: leaf split → parent split → root split.

**"Merge Cascade"**
> "A deletion sequence that triggers multiple merges propagating upward, then
> a root shrink."
- Pre-populated full tree, delete keys in an order that forces cascading merges.

**"Borrow Left and Right"**
> "Two deletions, each causing a different borrow direction. Observe the key
> rotation and how order is preserved."
- Demonstrates both BORROW_LEFT and BORROW_RIGHT in sequence.

**"Balanced by Design"**
> "After 20 random insertions and 5 deletions, verify that all leaves are still
> at the same depth. B-trees never become unbalanced."
- Ends with the Validate operation showing all invariants satisfied.

### 10.3 Scenario Playback

When a scenario is loaded:
1. A modal overlay appears with the scenario name, description, and a "Start" button.
2. On Start, the initial tree is built instantly (no animation) and the first
   operation begins.
3. Between operations, a 1.5-second pause shows the full tree in a resting state,
   then a small announcement appears: "Next: Insert(30)" before the next operation begins.
4. A scenario progress indicator shows "Operation 3 of 8".

---

## 11. Module Architecture

### 11.1 File Structure

```
btree-visualizer/
│
├── index.html                      ← HTML shell only (markup + CSS)
├── app.js                          ← Wiring only (imports all layers, no logic)
│
└── src/
    ├── index.js                    ← Public barrel export
    │
    ├── schema/
    │   └── index.js                ← State types, constants (ACTIONS, ROLES)
    │
    ├── core/
    │   ├── BTree.js                ← B-tree state manipulation (pure functions)
    │   ├── search.js               ← Search operation → Step[]
    │   ├── insert.js               ← Insert operation → Step[]
    │   ├── delete.js               ← Delete operation → Step[]
    │   └── shared.js               ← cloneState, generateId, createStep
    │
    ├── playback/
    │   └── PlaybackController.js   ← Identical contract to linked list version
    │
    ├── animation/
    │   ├── AnimationLayer.js       ← Main class, orchestrates sub-modules
    │   ├── LayoutEngine.js         ← computeLayout() pure function
    │   ├── NodeRenderer.js         ← D3 enter/update/exit for nodes + slots
    │   ├── EdgeRenderer.js         ← D3 enter/update/exit for edges
    │   ├── FloatLayer.js           ← Animated keys-in-flight (split/merge/borrow)
    │   ├── FocusController.js      ← Manages opacity of non-active nodes
    │   ├── CameraController.js     ← D3 zoom, auto-pan rules
    │   ├── MinimapRenderer.js      ← Minimap inset SVG
    │   └── ThemeModule.js          ← All colour/size/timing constants
    │
    ├── choreography/
    │   └── Choreographer.js        ← Maps action → ChoreographyPlan
    │
    └── narrative/
        ├── NarrativeLayer.js       ← Orchestrator (the only public import)
        ├── InvariantTracker.js     ← NEW: B-tree property display
        ├── RecursionDepth.js       ← NEW: call stack breadcrumb
        ├── ExplanationPanel.js     ← Rich text explanation
        ├── PseudocodePanel.js      ← Syntax-highlighted pseudocode
        ├── VariableInspector.js    ← Variable chips with diffing
        ├── ComplexityPanel.js      ← Time/space complexity per operation
        └── constants.js            ← PSEUDOCODES, COMPLEXITY_MAP, VAR_ROLES
```

### 11.2 Module Dependency Rules

```
  core/          imports from: schema/
  playback/      imports from: (nothing from this project)
  animation/     imports from: schema/, core/BTree.js (for getOrderedIds etc.)
  choreography/  imports from: schema/
  narrative/     imports from: schema/, narrative/constants.js
  app.js         imports from: src/index.js (barrel), all four layer main classes
```

No circular imports. The schema module is the only shared dependency between
all other modules.

### 11.3 app.js Wiring Pattern

```js
// Same pattern as linked list — only this file knows all layers exist

const anim = new AnimationLayer(svgEl, window.d3);
const narr = new NarrativeLayer({ /* DOM elements */ });
let ctrl = null;

function runOperation(op, key, t) {
  const state = buildInitialState(t, currentKeys);
  const steps = buildSteps(op, state, key);

  narr.loadOperation(op);                    // pre-flight: load pseudocode etc.
  if (ctrl) ctrl.destroy();                  // stop old controller

  ctrl = new PlaybackController(steps, { speed, pauseOnKeySteps: true });

  let prevStep = null;
  ctrl.on('frame',     step => anim.render(step));
  ctrl.on('narrative', step => { narr.update(step, prevStep); prevStep = step; });
  ctrl.on('statusChange', updatePlaybackUI);

  anim.render(steps[0]);
  narr.update(steps[0], null);
  anim.fitView(steps[0].state);
}
```

---

## 12. Implementation Order

Build in this exact order. Each stage is independently testable before
the next begins.

**Stage 1 — Core + Schema (no rendering)**
1. Define all ACTIONS, NODE_ROLES, KEY_ROLES, EDGE_ROLES constants
2. Implement BTree.js: state creation, insertion, deletion, validation (pure)
3. Implement shared.js: cloneState, generateId, createStep
4. Implement search.js, insert.js, delete.js → Step[] outputs
5. Unit tests: invariant preservation, step count, key ordering after each op

**Stage 2 — Layout Engine (no D3)**
1. Implement computeLayout() for nodes, slots, pointer dots, edges
2. Unit tests: node positions for known trees, edge counts, width formulas

**Stage 3 — Static Render**
1. Implement ThemeModule.js, NodeRenderer.js, EdgeRenderer.js
2. AnimationLayer renders a static tree (no transitions, just place everything)
3. Wire PlaybackController to AnimationLayer — verify frames render correctly

**Stage 4 — Transitions**
1. Implement Choreographer.js with timing plans for each action
2. Add enter/exit/move transitions to NodeRenderer and EdgeRenderer
3. Implement FloatLayer.js for keys-in-flight during split/merge/borrow

**Stage 5 — Camera**
1. Implement CameraController.js with all 6 camera rules
2. Implement MinimapRenderer.js

**Stage 6 — Focus System**
1. Implement FocusController.js — dim non-active nodes per operation phase

**Stage 7 — Narrative Layer**
1. InvariantTracker.js
2. RecursionDepth.js
3. ExplanationPanel.js, PseudocodePanel.js, VariableInspector.js, ComplexityPanel.js
4. NarrativeLayer.js orchestrator

**Stage 8 — Wiring & UI Shell**
1. index.html markup and CSS
2. app.js wiring
3. Playback controls, top bar interactions, key-step banner

**Stage 9 — Scenario Mode**
1. Scenario schema and loader
2. Built-in scenarios
3. Scenario progress indicator

**Stage 10 — Polish**
1. Refine choreography timings by visual testing each operation
2. Edge case handling: t=2 with 1-key trees, root splits, full merge cascades
3. Keyboard shortcuts for playback controls
4. Performance: test with t=2 and 50+ keys inserted

---

## 13. Testing Strategy

### 13.1 Core (Unit Tests)

Every operation must satisfy all B-tree invariants after completion. For each
operation test:

- All nodes (except root) have ≥ t-1 keys
- All nodes have ≤ 2t-1 keys
- All leaves are at the same depth
- Root has ≥ 1 key (if tree is non-empty)
- All parent-child relationships are consistent
- In-order traversal of the final tree yields a sorted sequence

Test cases for insert: empty tree, single key, fill to capacity, split leaf,
split internal node, split root, cascade (two consecutive splits).

Test cases for delete: delete from leaf (safe), delete from leaf (underflow →
borrow left), delete from leaf (underflow → borrow right), delete from leaf
(underflow → merge), delete from internal node (predecessor replacement),
cascading merge, root shrink.

### 13.2 Step Sequence Tests (Narrative Consistency)

For each operation:
- Every step's `pseudocodeLine` falls within the pseudocode array bounds
- `isKeyStep` steps occur at structurally important moments (not every step)
- `step.meta.phase` transitions correctly: descend → act → unwind
- `step.variables.node` always corresponds to a node in `step.state.nodes`

### 13.3 Layout Tests

- Node widths match the formula for each key count
- No two nodes overlap at any step
- Parent x falls within the horizontal span of its children
- All leaves share the same y coordinate

### 13.4 Animation Tests (Manual / Visual)

- Split: the crack appears before the halves move
- Borrow: the key arc completes before the sibling shrinks
- Merge: all three timing phases (fall, absorb, remove) fire in order
- Camera: never jumps without transition
- Focus: non-active nodes dim smoothly without flickering

---

## 14. Quality Checklist

Before shipping, every item must be verified:

**Educational**
- [ ] The InvariantTracker accurately reflects tree state on every step
- [ ] The RecursionDepth breadcrumb correctly tracks descent and unwind
- [ ] Every `isKeyStep` explanation answers both "what" and "why"
- [ ] Pseudocode line always matches the described algorithm action
- [ ] The split animation makes it obvious that the median goes UP, not sideways
- [ ] The borrow animation makes it obvious that three keys rotate (not two)
- [ ] The student can see at a glance when a node is full vs safe vs underflow

**Visual**
- [ ] The warm amber palette is clearly distinct from the linked list's cold navy
- [ ] Node slots read as individual units (the key is the unit, not the node)
- [ ] Leaf nodes are visually distinct from internal nodes
- [ ] The root badge and underflow badge are always legible
- [ ] Focus dimming never makes it impossible to see the tree structure

**Animation**
- [ ] No operation animates all elements simultaneously (choreography is staged)
- [ ] The split "crack" animation reads as dramatic and consequential
- [ ] The borrow "tumble" is visually clear about which key goes where
- [ ] The merge "gravity pull" feels satisfying, not abrupt
- [ ] The camera always finishes its transition before the next operation step fires
- [ ] The minimap viewport rectangle moves in sync with the main camera

**Robustness**
- [ ] t=2 (minimum valid t) works correctly throughout all operations
- [ ] t=5 (maximum supported) works correctly with wide nodes
- [ ] A tree with 1 node handles delete correctly
- [ ] All scenario pre-built cases complete without errors
- [ ] Destroying and recreating the controller between operations has no leaks

---

## 15. Deliberate Departures From the Linked-List Visualizer

To prevent this from becoming a reskin, these are the structural decisions
that make the B-tree visualizer its own product:

1. **The InvariantTracker is the sidebar centrepiece.** The linked list sidebar
   led with pseudocode. Here, the invariant tracker leads. This reflects that
   B-trees are *defined* by their invariants in a way linked lists are not.

2. **The unit of attention is the key slot, not the node.** The linked list
   highlighted entire nodes. Here, individual key slots within nodes are the
   primary highlight targets. The animations (split, borrow) operate at slot
   granularity.

3. **The FloatLayer.** The linked list never had elements that left their node
   and travelled through space. B-tree splits, merges, and borrows all involve
   keys in motion — a fundamentally different animation model.

4. **The RecursionDepth breadcrumb.** The linked list algorithm was iterative.
   B-tree algorithms are recursive and two-phased. Making the call stack visible
   is new.

5. **The camera is a first-class module.** The linked list had a simple pan.
   The two-level camera (main + minimap) with subtree-focus logic is required
   by the 2D nature of the tree.

6. **Warm vs cold palette.** Non-negotiable visual differentiation. A student
   using both visualisers should never confuse one for the other at a glance.

7. **Per-step key-step banner with reason codes.** "⚑ Overflow — split required"
   is richer than the generic "⚑ Key step" of the linked list.

8. **Scenario mode.** The linked list had no scenario mode. B-trees benefit from
   pre-built sequences because their educational value compounds across operations
   (a sequence of inserts that forces two splits tells a better story than a
   single isolated insert).

---

*End of document.*
