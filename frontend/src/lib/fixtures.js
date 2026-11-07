/* Sample payloads shaped exactly like the API contract in AGENTS.md.
   api.js serves these while VITE_USE_FIXTURES is on, so the screens are
   demoable before the endpoints exist. When an endpoint lands, the fixture
   for it stops being read. Do not import this file from a component. */

import { presetById } from './presets.js'

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

/* ---------- Signup ----------
   The POST /students response, built from the body the last onboarding step
   would have sent, so the aha screen shows numbers that match the schedule
   the student actually picked instead of a hardcoded Tuesday.

   The real endpoint counts rows. This counts nothing: it derives a plausible
   number from the gap, which is enough to build and demo the screen against
   and is replaced the moment the endpoint lands. */

const DAY_NAMES = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']

export function studentCreated(body) {
  /* Expanding preset_id into free blocks is the server's job, so the stand-in
     for the server does it here rather than making the caller pre-chew it. */
  const blocks =
    body.free_blocks ?? presetById(body.preset_id)?.free_blocks ?? []
  const block = blocks[0] ?? { day: 1, start: '13:00', end: '15:00' }
  const tag = (body.tags ?? [])[0] ?? null

  /* Never zero. The aha screen's whole job is the one encouraging number, and
     "0 people share your gap" is the worst first impression the app can make.
     The real endpoint falls back to the student's busiest-overlap gap for the
     same reason. */
  const freeCount = 9 + ((block.day * 7 + parseInt(block.start, 10)) % 14)

  return {
    student: {
      id: `fixture-${block.day}${block.start.replace(':', '')}`,
      first_name: body.first_name,
      paused: false,
      visibility: body.visibility ?? 'everyone',
    },
    aha: {
      gap: { day: DAY_NAMES[block.day] ?? 'tue', start: block.start, end: block.end },
      free_count: freeCount,
      same_tag_count: tag === null ? 0 : 1 + (freeCount % 4),
      tag,
    },
    /* Fixture mode stands in for demo mode, so a guest gets a token. */
    guest_token: body.guest === true ? 'fixture-guest-token' : null,
  }
}
