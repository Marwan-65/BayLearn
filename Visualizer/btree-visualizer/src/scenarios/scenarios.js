// src/scenarios/scenarios.js
//
// All built-in scenario definitions. Each scenario is a self-contained
// description of what tree to start with and which operations to perform.
//
// The schema follows spec section 10.1:
//   id           --, unique string key
//   name         --, display name in the dropdown
//   description  --, 1-2 sentence hook shown in the modal before playback
//   t            --, minimum degree (2–5)
//   initialKeys  --, keys pre-inserted silently before the scenario starts
//   operations   --, array of { op, key } to run in sequence
//   pauseMs      --, ms pause between sequential operations (default 1500)

const SCENARIOS = [
  {
    id:          'db-index',
    name:        'Database Index Builder',
    description: 'Watch a B-tree build itself as 15 records are indexed one by one. Notice how splits propagate upward and the tree grows in height.',
    t:           3,
    initialKeys: [],
    operations:  [10, 20, 5, 6, 12, 30, 7, 17, 3, 25, 8, 50, 45, 35, 40]
                   .map(k => ({ op: 'insert', key: k })),
    pauseMs:     1500,
  },

  {
    id:          'split-cascade',
    name:        'Split Cascade',
    description: 'A worst-case insertion sequence that triggers a chain of splits all the way to the root, increasing the tree height by one level.',
    t:           2,
    initialKeys: [1, 2, 3, 4, 5, 6],
    operations:  [{ op: 'insert', key: 7 }],
    pauseMs:     1200,
  },

  {
    id:          'merge-cascade',
    name:        'Merge Cascade',
    description: 'A deletion sequence that triggers multiple merges propagating upward, eventually causing a root shrink and reducing tree height.',
    t:           2,
    initialKeys: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    operations:  [10, 9, 8].map(k => ({ op: 'delete', key: k })),
    pauseMs:     1500,
  },

  {
    id:          'borrow',
    name:        'Borrow Left and Right',
    description: 'Two deletions, each causing a different borrow direction. Observe the three-way key rotation and how sorted order is always preserved.',
    t:           2,
    initialKeys: [10, 20, 30, 40, 50],
    operations:  [
      { op: 'delete', key: 40 },
      { op: 'delete', key: 10 },
    ],
    pauseMs:     1800,
  },

  {
    id:          'balanced',
    name:        'Balanced by Design',
    description: 'After 20 random insertions and 5 deletions, all leaves are still at the same depth. B-trees never become unbalanced.',
    t:           3,
    initialKeys: [],
    operations: [
      ...[15, 8, 22, 4, 12, 18, 30, 2, 6, 10, 14, 16, 20, 25, 35, 3, 7, 11, 19, 28]
        .map(k => ({ op: 'insert', key: k })),
      ...[4, 10, 22, 3, 7]
        .map(k => ({ op: 'delete', key: k })),
    ],
    pauseMs:     1200,
  },
];

// Keyed by id for fast lookup from app.js
const SCENARIO_MAP = Object.fromEntries(SCENARIOS.map(s => [s.id, s]));

module.exports = { SCENARIOS, SCENARIO_MAP };