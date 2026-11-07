/* Sample payloads shaped exactly like the API contract in AGENTS.md.
   api.js serves these while VITE_USE_FIXTURES is on, so the screens are
   demoable before the endpoints exist. When an endpoint lands, the fixture
   for it stops being read. Do not import this file from a component. */

export const meNow = {
  gap: { day: 'tue', start: '13:00', end: '15:00' },
  group: {
    id: 'g_41',
    members: ['Ji-woo', 'Amir', 'Rosa'],
    shared: ['STAT 302', '2 transfers', 'Speaks Korean', 'Into guitar'],
    spot: { building: 'The Nest', walk_min: 4 },
    response: 'pending',
  },
}

export const projector = {
  joined: 18,
  groups: 4,
  alone: 2,
}

/* No endpoint for these two yet. See the notes in api.js. */

export const openTables = [
  { id: 't_1', building: 'Koerner', detail: '2nd floor', seats: 2, mode: 'study', until: '14:30' },
  { id: 't_2', building: 'Nest', detail: 'food court', seats: 3, mode: 'social', until: '14:00' },
]

export const me = {
  first_name: 'Sothea',
  tags: ['transfer', 'commuter'],
  hangouts_count: 3,
  paused: false,
}
