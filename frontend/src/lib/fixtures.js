/* Sample payloads shaped exactly like the API contract in docs/AGENTS.md.
   api.js serves these only while VITE_USE_FIXTURES=true, which is how the
   screens stay workable with the backend stopped. Every shape here is the
   real one; if an endpoint changes, this file changes in the same commit.
   Do not import this file from a component. */

import { presetById } from './presets.js'

/* ---------- Right now ---------- */

export const meNow = {
  gap: { day: 'tue', start: '13:00', end: '15:00' },
  group: {
    id: 'g_41',
    state: 'confirmed',
    mode: 'social',
    members: [
      { first_name: 'You', top_badge: { slug: 'regular', name: 'Regular' } },
      { first_name: 'Ji-woo', top_badge: { slug: 'first_hello', name: 'First Hello' } },
      { first_name: 'Amir', top_badge: null },
    ],
    shared: ['STAT 302', '2 transfers', 'Speaks Korean'],
    /* No spot while my_state is 'invited'. The backend will not send one:
       spot_is_visible_to() in app/groups_view.py needs the caller to have
       joined, not merely to have been invited. A fixture that showed the
       building here would teach the opposite of the rule the server
       enforces, and screens built against it would break on real data. */
    spot: null,
    joined_count: 3,
    checked_in_count: 0,
    seats_left: 2,
    my_state: 'invited',
    needs: 0,
  },
}

/* No names, no exact spot. What a student sees before joining is the time,
   the general area and what the group shares. */
export const openGroups = [
  {
    id: 'g_52',
    gap: { day: 'tue', start: '13:00', end: '14:30' },
    mode: 'study',
    area: 'Koerner Library',
    seats_left: 2,
    shared: ['2 transfers'],
  },
  {
    id: 'g_53',
    gap: { day: 'tue', start: '13:30', end: '15:00' },
    mode: 'social',
    area: 'The Nest',
    seats_left: 1,
    shared: ['Speaks Cantonese'],
  },
]

export function startedGroup({ building, mode }) {
  return {
    id: 'g_new',
    state: 'forming',
    mode,
    members: [{ first_name: 'You', top_badge: null }],
    shared: [],
    /* Forming, so no spot comes back even though the student picked the
       building. The screen remembers their own choice instead. */
    spot: null,
    joined_count: 1,
    checked_in_count: 0,
    seats_left: 4,
    my_state: 'joined',
    needs: 2,
    building,
  }
}

/* ---------- Map ----------

   Counts, never names. A count is not a name, and anything under three is
   absent rather than shown, so nobody can be singled out by a pin.

   Coordinates match backend/app/demo.py and were checked against current
   OpenStreetMap/UBC location references. */

export const campusMap = {
  buildings: [
    { slug: 'nest', name: 'The Nest', lat: 49.2665578, lng: -123.2498368, free_count: 12 },
    { slug: 'ikb', name: 'Irving K Barber Learning Centre', lat: 49.2676194, lng: -123.252761, free_count: 7, groups_meeting: 2 },
    { slug: 'koerner', name: 'Koerner Library', lat: 49.2665489, lng: -123.255078, free_count: 5, groups_meeting: 1 },
    { slug: 'life', name: 'Life Building', lat: 49.2674326, lng: -123.2500649, free_count: 3, groups_meeting: 1 },
  ],
  my_group: {
    group_id: 'g_41',
    slug: 'nest',
    name: 'The Nest',
    lat: 49.2665578,
    lng: -123.2498368,
    joined_count: 4,
    checked_in_count: 2,
    state: 'active',
  },
}

/* ---------- Projector ---------- */

/* Mirrors GET /me's `badges`, from backend/app/badges.py. */
export const badges = [
  {
    slug: 'community_host',
    name: 'Community Host',
    earned: true,
    progress: { current: 1, target: 1 },
  },
  {
    slug: 'social_regular',
    name: 'Social Regular',
    earned: false,
    progress: { current: 1, target: 3 },
  },
  {
    slug: 'study_regular',
    name: 'Study Regular',
    earned: false,
    progress: { current: 0, target: 3 },
  },
  {
    slug: 'super_host',
    name: 'Super Host',
    earned: false,
    progress: { current: 1, target: 5 },
  },
]

export const projector = {
  forming: 3,
  confirmed: 4,
  checked_in: 11,
  students: 26,
  dots: [
    { slug: 'nest', name: 'The Nest', lat: 49.2665578, lng: -123.2498368, count: 12 },
    { slug: 'koerner', name: 'Koerner Library', lat: 49.2665489, lng: -123.255078, count: 5 },
  ],
}


/* ---------- Onboarding options ----------
   Mirrors GET /options, whose ids come from the database lookup tables. */

export const options = {
  languages: [
    { id: 'en', label: 'English' },
    { id: 'zh', label: 'Mandarin Chinese' },
    { id: 'ko', label: 'Korean' },
  ],
  tags: [
    { id: 'international', label: 'International student' },
    { id: 'transfer', label: 'Transfer student' },
    { id: 'commuter', label: 'Commuter' },
  ],
  buildings: [
    { id: 'nest', label: 'The Nest' },
    { id: 'ikb', label: 'Irving K Barber Learning Centre' },
    { id: 'koerner', label: 'Koerner Library' },
    { id: 'life', label: 'Life Building' },
    { id: 'buchanan', label: 'Buchanan Courtyard' },
    { id: 'angus', label: 'Henry Angus' },
    { id: 'icics', label: 'ICICS' },
    { id: 'woodward', label: 'Woodward Library' },
  ],
}

/* ---------- Signup ----------
   The POST /students response, built from the body the last onboarding step
   would have sent, so the aha screen shows numbers that match the schedule
   the student actually picked instead of a hardcoded Tuesday.

   The real endpoint counts rows. This counts nothing: it derives a plausible
   number from the gap, which is enough to build the screen against. */

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
      is_guest: body.guest === true,
      paused: false,
      visibility: body.visibility ?? 'everyone',
      tags: body.tags ?? [],
      favourite_spots: body.favourite_spots ?? [],
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
