/* The preset schedules onboarding step 2 offers.

   A student picks one instead of typing a timetable, which is the whole point
   of tier 1 signup: a stage audience is onboarded in seconds and the group
   optimizer still has real free blocks to work with. Gemini screenshot
   parsing (tier 2) produces `free_blocks` in the same shape and skips this
   list entirely.

   `id` is a contract. POST /students sends it, backend/app/presets.py
   expands it into free_blocks rows, and backend/seed.py gives its fake
   students the same ids. Changing or removing one means changing all three,
   so add rather than rename.

   `day` is 0 for Monday, matching the free_blocks table in
   backend/schema.sql. Times are 24-hour local. Blocks are the gaps BETWEEN
   classes, not the classes, because free time is the only thing the matcher
   reads and the only thing any other student is ever shown. */

export const PRESETS = [
  {
    id: 'mwf-midday',
    label: 'Mon, Wed, Fri with a midday gap',
    blurb: 'Free around lunch three days a week',
    free_blocks: [
      { day: 0, start: '12:00', end: '14:00' },
      { day: 2, start: '12:00', end: '15:00' },
      { day: 4, start: '12:00', end: '14:00' },
    ],
  },
  {
    id: 'tue-thu-afternoons',
    label: 'Tue, Thu afternoons',
    blurb: 'Two long afternoon gaps',
    free_blocks: [
      { day: 1, start: '13:00', end: '15:00' },
      { day: 3, start: '13:00', end: '15:00' },
    ],
  },
  {
    id: 'tue-thu-mornings',
    label: 'Tue, Thu mornings',
    blurb: 'Early classes, then free before noon',
    free_blocks: [
      { day: 1, start: '10:00', end: '12:00' },
      { day: 3, start: '10:00', end: '12:00' },
    ],
  },
  {
    id: 'long-wednesday',
    label: 'One long Wednesday gap',
    blurb: 'A four-hour hole in the middle of the week',
    free_blocks: [{ day: 2, start: '11:00', end: '15:00' }],
  },
  {
    id: 'commuter-two-days',
    label: 'On campus Mon and Wed only',
    blurb: 'Long days, two days a week',
    free_blocks: [
      { day: 0, start: '11:00', end: '13:00' },
      { day: 0, start: '15:00', end: '17:00' },
      { day: 2, start: '11:00', end: '13:00' },
      { day: 2, start: '15:00', end: '17:00' },
    ],
  },
  {
    id: 'late-starts',
    label: 'Late starts most days',
    blurb: 'Free mornings, classes from the afternoon',
    free_blocks: [
      { day: 0, start: '10:00', end: '12:00' },
      { day: 1, start: '10:00', end: '12:00' },
      { day: 3, start: '10:00', end: '12:00' },
    ],
  },
  {
    id: 'evening-classes',
    label: 'Evening classes',
    blurb: 'Free late afternoon before a 6pm lecture',
    free_blocks: [
      { day: 1, start: '16:00', end: '18:00' },
      { day: 3, start: '16:00', end: '18:00' },
    ],
  },
]

export function presetById(id) {
  return PRESETS.find((p) => p.id === id) ?? null
}

/* ---------- Step 3's options ----------
   The tag slugs match the `tags` lookup table in backend/schema.sql, and the
   four student types named in AGENTS.md come first because newcomer priority
   in the optimizer keys off them. */

export const STUDENT_TAGS = [
  { slug: 'international', label: 'International' },
  { slug: 'transfer', label: 'Transfer' },
  { slug: 'exchange', label: 'Exchange' },
  { slug: 'commuter', label: 'Commuter' },
  { slug: 'first-year', label: 'First year' },
  { slug: 'grad', label: 'Grad student' },
]

/* ISO 639-1, matching the `languages` table. A short list keeps step 3 to one
   screen; the table holds the rest. */
export const LANGUAGES = [
  { code: 'en', name: 'English' },
  { code: 'zh', name: 'Mandarin' },
  { code: 'yue', name: 'Cantonese' },
  { code: 'ko', name: 'Korean' },
  { code: 'ja', name: 'Japanese' },
  { code: 'pa', name: 'Punjabi' },
  { code: 'hi', name: 'Hindi' },
  { code: 'fa', name: 'Persian' },
  { code: 'es', name: 'Spanish' },
  { code: 'fr', name: 'French' },
  { code: 'km', name: 'Khmer' },
  { code: 'tl', name: 'Tagalog' },
  { code: 'ar', name: 'Arabic' },
  { code: 'vi', name: 'Vietnamese' },
]

export const VISIBILITY_OPTIONS = [
  {
    value: 'everyone',
    label: 'Anyone who is free when I am',
    blurb: 'The most people to hang out with',
  },
  {
    value: 'my_courses',
    label: 'Only people in my courses',
    blurb: 'Smaller groups, more in common',
  },
  {
    value: 'shared_tag',
    label: 'Only people who share a tag with me',
    blurb: 'For example other transfers or commuters',
  },
]
