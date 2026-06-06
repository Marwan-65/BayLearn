
//hena kol el sceanrios fiha el trees bad2a ezay w eh el operations bl values bta3etha
//simple
const SCENARIOS = [
  {
    id:          'db-index',
    name:        'Database Index Builder',
    description: 'Watch a B-tree build itself as 15 records are indexed one by one. Notice how splits propagate upward and the tree grows in height.', //e7gehu8
    t:           3,
    initialKeys: [],
    operations:  [10, 20, 5, 6, 12, 30, 7, 17, 3, 25, 8, 50, 45, 35, 40]
                   .map(k => ({ op: 'insert', key: k })), // ba7awel el array of key l array of operations 7sb el format el gdida
    pauseMs:     1500,
  },

  {
    id:          'split-cascade',
    name:        'Split Cascade',
    description: 'A worst-case insertion sequence that triggers a chain of splits all the way to the root, increasing the tree height by one level.', ///838ghjegud
    t:           2,
    initialKeys: [1, 2, 3, 4, 5, 6],
    operations:  [{ op: 'insert', key: 7 }],
    pauseMs:     1200,
  },

  {
    id:          'merge-cascade',
    name:        'Merge Cascade',
    description: 'A deletion sequence that triggers multiple merges propagating upward, eventually causing a root shrink and reducing tree height.', //da kda el scenario edh88s w sa3etha
    t:           2,
    initialKeys: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    operations:  [10, 9, 8].map(k => ({ op: 'delete', key: k })),
    pauseMs:     1500,
  },

  {
    id:          'borrow',
    name:        'Borrow Left and Right',
    description: 'Two deletions, each causing a different borrow direction. Observe the three-way key rotation and how sorted order is always preserved.', /// w da kman hena by bprrow
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

//e3mel key by iD 3shan el llokup yeb2a sahl mn el main
const SCENARIO_MAP = Object.fromEntries(SCENARIOS.map(s => [s.id, s]));

module.exports = { SCENARIOS, SCENARIO_MAP };