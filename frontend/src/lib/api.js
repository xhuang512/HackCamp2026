/* The only file in the frontend that calls the backend.
   Components call these functions and never fetch directly.
   Shapes follow the API contract in docs/AGENTS.md. Changing one is a
   team-wide change, so raise it before editing a response shape here. */

import * as fixtures from './fixtures.js'

/* Vite inlines VITE_ vars into the public bundle, so only public values here.
   VITE_API_URL is unset in dev: requests go to /api and vite.config.js
   proxies them to the FastAPI server. The trailing slash is stripped because
   `${BASE}${path}` would otherwise build '//me'. */
const BASE = (import.meta.env.VITE_API_URL ?? '/api').replace(/\/+$/, '')

/* Off by default now that the endpoints exist. Set VITE_USE_FIXTURES=true in
   .env.local to work on the screens with the backend stopped. */
const USE_FIXTURES = import.meta.env.VITE_USE_FIXTURES === 'true'

const SESSION_KEY = 'hangout.session'
export const SESSION_EXPIRED_EVENT = 'hangout:session-expired'
/* Fixture mode only. Holds the profile that POST /students "created", so the
   route gate can tell a new student from a returning one with the backend
   switched off. Never read when USE_FIXTURES is false. */
const FIXTURE_STUDENT_KEY = 'hangout.fixtureStudent'

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/* ---------- The token ----------
   Two kinds, both sent as `Authorization: Bearer`, never a cookie: the
   frontend and backend sit on different domains and Safari blocks cross-site
   cookies.

     Auth0 access token  Fetched per request by the provider that
                         src/lib/auth.jsx registers, because it expires and
                         only the SDK can refresh it.
     Guest token         Issued by POST /students in demo mode and kept in
                         localStorage. */

let tokenProvider = null

/** Called by src/lib/auth.jsx. Pass null to unregister. */
export function setTokenProvider(fn) {
  tokenProvider = fn
}

export function getSession() {
  try {
    return localStorage.getItem(SESSION_KEY)
  } catch {
    /* Private browsing can throw on access. */
    return null
  }
}

export function setSession(token) {
  try {
    if (token === null) localStorage.removeItem(SESSION_KEY)
    else localStorage.setItem(SESSION_KEY, token)
  } catch {
    /* Nothing to do. The next request goes out unauthenticated. */
  }
}

async function bearer() {
  if (tokenProvider !== null) {
    const token = await tokenProvider()
    if (token) return token
  }
  return getSession()
}

async function request(path, { method = 'GET', body, signal } = {}) {
  const token = await bearer()
  /* POST /schedule/parse is the one route that sends a file. FormData must go
     out as-is and without a Content-Type header, because only the browser
     knows the multipart boundary it generated. Setting the header by hand
     here is what makes FastAPI answer 422 on a perfectly good upload. */
  const form = typeof FormData !== 'undefined' && body instanceof FormData
  let res
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      signal,
      headers: {
        ...(body === undefined || form ? {} : { 'Content-Type': 'application/json' }),
        ...(token === null ? {} : { Authorization: `Bearer ${token}` }),
      },
      ...(body === undefined ? {} : { body: form ? body : JSON.stringify(body) }),
    })
  } catch (cause) {
    if (cause?.name === 'AbortError') throw cause
    throw new ApiError('Could not reach the server.', 0)
  }

  if (!res.ok) {
    /* A reset or expiry can invalidate a guest token. Clearing it here keeps
       the route gate from retrying a dead session forever. Auth0 tokens are
       owned by the SDK and never live under SESSION_KEY. */
    if (res.status === 401 && getSession() !== null) {
      setSession(null)
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT))
      }
    }
    throw new ApiError(await messageFor(res, method, path), res.status)
  }
  if (res.status === 204) return null
  return res.json()
}

/* FastAPI puts the reason in `detail`, and those strings are written for a
   student to read ("Join the group before checking in."). Showing
   "POST /groups returned 422" instead throws that away. */
async function messageFor(res, method, path) {
  try {
    const body = await res.json()
    if (typeof body?.detail === 'string') return body.detail
    /* A 422 from pydantic's own validation is a list of errors rather than a
       sentence, and every message in it is prefixed "Value error, ". Without
       this the student reads "PUT /me/schedule returned 422". */
    if (Array.isArray(body?.detail) && typeof body.detail[0]?.msg === 'string') {
      return body.detail[0].msg.replace(/^Value error, /, '')
    }
  } catch {
    /* Not JSON, or an empty body. Fall through to the generic line. */
  }
  return `${method} ${path} returned ${res.status}`
}

/* ---------- Identity ---------- */

/** GET /me — does the signed-in user have a profile yet? The route gate calls
    this on every app open, so it is the one request between the splash screen
    and the first real screen. Keep it cheap.

      { "onboarded": false }
      { "onboarded": true, "student": { id, first_name, is_guest, paused,
                                        visibility, tags, favourite_spots,
                                        free_blocks: [{ day, start_time,
                                                        end_time }] },
                              "badges": [{ slug, name, earned,
                                           progress: { current, target } }] }

    A student with deleted_at set counts as not onboarded. */
export async function getMe({ signal } = {}) {
  if (USE_FIXTURES) {
    const student = readFixtureStudent()
    return student === null
      ? { onboarded: false, badges: [] }
      : { onboarded: true, student, badges: fixtures.badges }
  }
  return request('/me', { signal })
}

/** POST /students — create the profile at the end of onboarding.

    `auth_sub` is deliberately absent from the body. The backend takes it from
    the verified token, so nobody can create a profile for someone else.
    Send either preset_id or free_blocks, never both.

    `courses` are codes like "STAT 302", normalised by src/lib/courses.js to
    match what the backend accepts. They are what puts a shared course at the
    front of a group's `shared` list, which is the strongest line on a group
    card. They do not affect who is matched: engine.form_groups() groups on
    overlapping free time alone.

    One backend requirement to know about: a non-empty `courses` with the
    server's CURRENT_TERM unset fails the whole request with 503, not 422,
    because an unset variable is the server's fault rather than the caller's.
    Onboarding offers to retry without them rather than leaving someone
    stuck behind a variable only the backend owner can set.

    Returns { student, aha, guest_token }. A guest_token comes back only when
    `guest` is true and the backend's DEMO_MODE is on; it is stored here so the
    next request is authenticated. */
export async function createStudent({
  first_name,
  preset_id = null,
  free_blocks = null,
  tags = [],
  courses = [],
  languages = [],
  ask_me_about = null,
  favourite_spots = [],
  visibility = 'everyone',
  guest = false,
}) {
  const body = {
    first_name,
    preset_id,
    free_blocks,
    tags,
    courses,
    languages,
    ask_me_about,
    favourite_spots,
    visibility,
    guest,
  }

  if (USE_FIXTURES) {
    const out = fixtures.studentCreated(body)
    writeFixtureStudent(out.student)
    if (out.guest_token !== null) setSession(out.guest_token)
    return out
  }

  const out = await request('/students', { method: 'POST', body })
  if (out?.guest_token) setSession(out.guest_token)
  return out
}

/** PATCH /me — name, tags, visibility, favourite spots, paused.

    Partial: send only what changed. Omitting a field leaves it alone, so the
    Me tab's pause switch cannot blank the student's tags. */
export async function patchMe(changes) {
  if (USE_FIXTURES) {
    const student = readFixtureStudent()
    const next = { ...(student ?? {}), ...changes }
    writeFixtureStudent(next)
    return next
  }
  return request('/me', { method: 'PATCH', body: changes })
}

/** Pause or resume matching. The Me tab's switch and the paused banner both
    call it.

    Not a cosmetic toggle: the matcher reads it, so a paused student is in no
    group it forms. */
export async function setPaused(paused) {
  return patchMe({ paused })
}

/** GET /options — the language and tag lists POST /students accepts.

    The ids are a contract with the database's lookup tables, so the Me tab
    and onboarding read them from here rather than from a hardcoded list that
    can drift. src/lib/presets.js holds the offline fallback. */
export async function getOptions({ signal } = {}) {
  if (USE_FIXTURES) return fixtures.options
  return request('/options', { signal })
}

/* ---------- Right now ---------- */

/** GET /me/now — the next gap and the suggested group.

      { gap: { day, start, end } | null,
        group: { id, state, mode,
                 members: [{ first_name, top_badge: { slug, name } | null }],
                 shared, spot, joined_count,
                 checked_in_count, seats_left, my_state, needs } | null }

    `group` is null when nothing has been suggested, and the screen falls back
    to getOpenGroups(). `spot` is null while the group is forming, because the
    meeting spot is hidden until the group is confirmed. */
export async function getMeNow({ signal } = {}) {
  if (USE_FIXTURES) return fixtures.meNow
  return request('/me/now', { signal })
}

/** GET /groups/open — confirmed groups in the caller's gap with seats left.
    No names and no exact spot: the time, the general area, what they share. */
export async function getOpenGroups({ signal } = {}) {
  if (USE_FIXTURES) return fixtures.openGroups
  return request('/groups/open', { signal })
}

/** POST /groups — start a group for a gap at a building the student picks.

    `now` is the "I'm free now" case: the group starts at this minute instead
    of at the next gap. The founder picked the spot, so they already know it;
    the API still hides it until the group confirms, which is the same rule
    for everyone. */
export async function createGroup({ building, mode = 'social', now = false }) {
  if (USE_FIXTURES) return fixtures.startedGroup({ building, mode })
  return request('/groups', { method: 'POST', body: { building, mode, now } })
}

/** GET /groups/{id} — members only. A non-member gets 404, not 403, so a
    stranger cannot learn that the group exists. */
export async function getGroup(groupId, { signal } = {}) {
  if (USE_FIXTURES) return fixtures.meNow.group
  return request(`/groups/${encodeURIComponent(groupId)}`, { signal })
}

/** POST /groups/{id}/join */
export async function joinGroup(groupId) {
  if (USE_FIXTURES) return { group_id: groupId, response: 'joined' }
  return request(`/groups/${encodeURIComponent(groupId)}/join`, { method: 'POST' })
}

/** POST /groups/{id}/skip */
export async function skipGroup(groupId) {
  if (USE_FIXTURES) return { group_id: groupId, response: 'skipped' }
  return request(`/groups/${encodeURIComponent(groupId)}/skip`, { method: 'POST' })
}

/* ---------- Check in ---------- */

/** GET /groups/{id}/checkin-code — the caller's current code.

    Returns { code, typed, expires_in }. `code` is the QR payload, which
    nobody types. `typed` is a six-digit fallback for a phone whose camera
    will not open; POST /groups/{id}/checkin takes either. Both rotate every
    30 seconds, so the screen showing them re-asks when expires_in runs
    out. */
export async function getCheckinCode(groupId, { signal } = {}) {
  if (USE_FIXTURES) {
    return { code: 'hc1.fixture.0.fixture', typed: '482716', expires_in: 30 }
  }
  return request(`/groups/${encodeURIComponent(groupId)}/checkin-code`, { signal })
}

/** POST /groups/{id}/checkin — submit a groupmate's scanned code.

    Checks both people in. `counted` is false when the pair had already
    checked each other in: the scan worked and changed nothing. `new_badges`
    contains only thresholds the caller crossed during this request. */
export async function postCheckin(groupId, code) {
  if (USE_FIXTURES) {
    return {
      joined_count: 3,
      checked_in_count: 2,
      my_state: 'checked_in',
      counted: true,
      new_badges: [{ slug: 'first_hello', name: 'First Hello' }],
    }
  }
  return request(`/groups/${encodeURIComponent(groupId)}/checkin`, {
    method: 'POST',
    body: { code },
  })
}

/* ---------- Schedule ---------- */

/** POST /schedule/parse — read a timetable screenshot into suggested blocks.

    Sends the image as multipart form data. The backend passes it to Gemini,
    returns suggestions, and keeps nothing: no file on disk, no row, no copy
    in the response. Nothing here may change that, because the promise that
    a timetable stays private to its owner is the reason students upload one.

      { timed_events: [{ weekday, date, start_time, end_time, title,
                         course_code, event_type }],
        all_day_events: [{ weekday, date, title, event_type }],
        warnings: [string],
        suggested_free_blocks: [{ day, start_time, end_time }],
        matching_window: { timezone, days, start_time, end_time },
        availability_status: "suggested_not_confirmed" }

    Throws ApiError with status 503 when no Gemini key is configured, and 422
    when the image is not a readable timetable. ScheduleEditor turns both into
    their own sentence, so keep the status on the error. */
export async function parseSchedule(image, { signal } = {}) {
  if (USE_FIXTURES) {
    return {
      timed_events: [],
      all_day_events: [],
      warnings: ['Fixture mode does not look at the image you chose.'],
      suggested_free_blocks: [
        { day: 1, start_time: '13:00', end_time: '15:00' },
        { day: 3, start_time: '09:30', end_time: '11:00' },
      ],
      matching_window: {
        timezone: 'America/Vancouver',
        days: [0, 1, 2, 3, 4],
        start_time: '09:00',
        end_time: '18:00',
      },
      availability_status: 'suggested_not_confirmed',
    }
  }
  const form = new FormData()
  form.append('image', image)
  return request('/schedule/parse', { method: 'POST', body: form, signal })
}

/** PUT /me/schedule — replace the caller's free blocks with reviewed ones.

    A replace, not a merge. Whatever is sent becomes the whole schedule, which
    is why ScheduleEditor must open with the blocks GET /me returned.

      { status: "saved", free_blocks: [{ day, start_time, end_time }] } */
export async function saveSchedule(freeBlocks) {
  if (USE_FIXTURES) return { status: 'saved', free_blocks: freeBlocks }
  return request('/me/schedule', {
    method: 'PUT',
    body: { free_blocks: freeBlocks },
  })
}

/* ---------- Map and projector ---------- */

/** GET /map — building activity, plus the caller's group building once the
    group is confirmed.

      { buildings: [{ slug, name, lat, lng, free_count }],
        my_group: { group_id, slug, name, lat, lng, joined_count,
                    checked_in_count } | null }

    Takes no position argument, and must not grow one. There is deliberately
    no parameter through which the student's coordinates could reach the
    backend. The server decides what is public from the group and building
    rows; the phone never tells it where it is. See src/lib/useMyLocation.js
    for the rest of that boundary.

    Buildings with fewer than three students are absent rather than shown with
    a small number, so nobody can be singled out by a pin. */
export async function getMap({ signal } = {}) {
  if (USE_FIXTURES) return fixtures.campusMap
  return request('/map', { signal })
}

/** GET /projector — anonymous totals and dots for the stage. No login. */
export async function getProjector({ signal } = {}) {
  if (USE_FIXTURES) return fixtures.projector
  return request('/projector', { signal })
}

/** POST /admin/reset — re-run the seed. Demo mode only. */
export async function adminReset() {
  if (USE_FIXTURES) return { status: 'reset' }
  return request('/admin/reset', { method: 'POST' })
}

/** GET /auth/config — what the backend thinks it is configured for.

    Public and callable before sign-in, which is the point: it is the only
    way the frontend can know whether the backend will actually issue a guest
    token. VITE_DEMO_MODE is the frontend's own opinion and the two disagree
    whenever only one of them is set.

      { demo_mode, guest_token_secret_set,
        auth0: { configured, domain, audience, problem } }

    It reports secrets as set or unset and never reads them back. The domain
    and audience are already in the public bundle.

    No fixture branch: there is no backend to describe in fixture mode, and a
    made-up answer here would hide the exact misconfiguration this is for.
    Callers handle the failure instead. */
export async function getAuthConfig({ signal } = {}) {
  return request('/auth/config', { signal })
}

/** GET /health — the one endpoint that existed first. */
export async function getHealth({ signal } = {}) {
  return request('/health', { signal })
}

/* ---------- Fixture-mode profile store ----------
   Without this, fixture mode has to answer GET /me the same way forever, so
   either onboarding or Right now is unreachable and the screens cannot be
   worked on with the backend stopped. Not used once VITE_USE_FIXTURES is
   anything but 'true'. */

function readFixtureStudent() {
  try {
    const raw = localStorage.getItem(FIXTURE_STUDENT_KEY)
    return raw === null ? null : JSON.parse(raw)
  } catch {
    return null
  }
}

function writeFixtureStudent(student) {
  try {
    localStorage.setItem(FIXTURE_STUDENT_KEY, JSON.stringify(student))
  } catch {
    /* The gate will treat them as not onboarded next open. Nothing better to
       do here, and it must not break the signup that just succeeded. */
  }
}

/** Called on log out. A no-op against a real backend. */
export function clearFixtureStudent() {
  try {
    localStorage.removeItem(FIXTURE_STUDENT_KEY)
  } catch {
    /* Nothing to do. */
  }
}

export const usingFixtures = USE_FIXTURES
