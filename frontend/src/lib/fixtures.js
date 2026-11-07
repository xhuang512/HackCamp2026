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

/* Hangouts happening now, for the map. Shaped off `groups` joined to
   `buildings` in backend/schema.sql.

   No names. A public surface gets a mode, a place, a joined count and an
   end time, and nothing else. A count is not a name.

   Only status 'active' rows belong on the map. A 'proposed' group would
   expose a match before the group has opted in, which the "meeting spots
   revealed only after the group opts in" rule forbids.

   COORDINATES ARE APPROXIMATE AND UNVERIFIED. See the warning at the top
   of mapConfig.js: check every lat/lng on a real map before the demo. */

export const hangoutsNow = [
  {
    id: 'g_41',
    mode: 'social',
    status: 'active',
    start: '13:00',
    end: '15:00',
    size: 4,
    building: { slug: 'nest', name: 'The Nest', lat: 49.2666, lng: -123.2497 },
  },
  {
    id: 'g_42',
    mode: 'study',
    status: 'active',
    start: '13:15',
    end: '14:30',
    size: 3,
    building: { slug: 'ikb', name: 'Irving K Barber', lat: 49.2675, lng: -123.2527 },
  },
  {
    id: 'g_43',
    mode: 'study',
    status: 'active',
    start: '12:30',
    end: '14:00',
    size: 5,
    building: { slug: 'koerner', name: 'Koerner Library', lat: 49.2679, lng: -123.2555 },
  },
  {
    id: 'g_44',
    mode: 'social',
    status: 'active',
    start: '13:30',
    end: '14:15',
    size: 3,
    building: { slug: 'life', name: 'Life Building', lat: 49.2663, lng: -123.2487 },
  },
]
