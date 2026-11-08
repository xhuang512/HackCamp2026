/* The only file in the frontend that calls the backend.
   Components call these functions and never fetch directly.
   Shapes follow the API contract in AGENTS.md. Changing one is a team-wide
   change, so raise it before editing a response shape here. */

import * as fixtures from './fixtures.js'

/* Vite inlines VITE_ vars into the public bundle, so only public values here.
   VITE_API_URL is unset in dev: requests go to /api and vite.config.js
   proxies them to the FastAPI server on :8000. */
const BASE = import.meta.env.VITE_API_URL ?? '/api'

/* On until the endpoints exist. Set VITE_USE_FIXTURES=false in .env.local to
   talk to the real backend. */
const USE_FIXTURES = import.meta.env.VITE_USE_FIXTURES !== 'false'

const SESSION_KEY = 'hangout.session'
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
  let res
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      signal,
      headers: {
        ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
        ...(token === null ? {} : { Authorization: `Bearer ${token}` }),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    })
  } catch (cause) {
    if (cause?.name === 'AbortError') throw cause
    throw new ApiError('Could not reach the server.', 0)
  }

  if (!res.ok) {
    throw new ApiError(`${method} ${path} returned ${res.status}`, res.status)
  }
  if (res.status === 204) return null
  return res.json()
}

/* ---------- Endpoints in the contract ---------- */

/** GET /me — does the signed-in user have a profile yet? The route gate calls
    this on every app open, so it is the one request between the splash screen
    and the first real screen. Keep it cheap.

      { "onboarded": false }
      { "onboarded": true, "student": { id, first_name, paused, visibility } }

    A student with deleted_at set counts as not onboarded. */
export async function getMe({ signal } = {}) {
  if (USE_FIXTURES) {
    const student = readFixtureStudent()
    return student === null ? { onboarded: false } : { onboarded: true, student }
  }
  return request('/me', { signal })
}

/** POST /students — create the profile at the end of onboarding.

    `auth_sub` is deliberately absent from the body. The backend takes it from
    the verified token, so nobody can create a profile for someone else.
    Send either preset_id or free_blocks, never both.

    Returns { student, aha, guest_token }. A guest_token comes back only when
    `guest` is true and the backend's DEMO_MODE is on; it is stored here so the
    next request is authenticated. */
export async function createStudent({
  first_name,
  preset_id = null,
  free_blocks = null,
  tags = [],
  languages = [],
  ask_me_about = null,
  visibility = 'everyone',
  guest = false,
}) {
  const body = {
    first_name,
    preset_id,
    free_blocks,
    tags,
    languages,
    ask_me_about,
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

/** GET /me/now — the next gap and the suggested group. */
export async function getMeNow({ signal } = {}) {
  if (USE_FIXTURES) return fixtures.meNow
  return request('/me/now', { signal })
}

/** POST /groups/{id}/join */
export async function joinGroup(groupId) {
  if (USE_FIXTURES) return { response: 'joined' }
  return request(`/groups/${encodeURIComponent(groupId)}/join`, { method: 'POST' })
}

/** POST /groups/{id}/skip */
export async function skipGroup(groupId) {
  if (USE_FIXTURES) return { response: 'skipped' }
  return request(`/groups/${encodeURIComponent(groupId)}/skip`, { method: 'POST' })
}

/** GET /projector — counts and anonymous group positions for the stage. */
export async function getProjector({ signal } = {}) {
  if (USE_FIXTURES) return fixtures.projector
  return request('/projector', { signal })
}

/** POST /admin/reset — re-run the seed. Demo mode only. */
export async function adminReset() {
  if (USE_FIXTURES) return { ok: true }
  return request('/admin/reset', { method: 'POST' })
}

/** GET /health — the one endpoint that existed first. */
export async function getHealth({ signal } = {}) {
  return request('/health', { signal })
}

/* ---------- Not in the contract yet ----------
   The Map and Me screens need these, but AGENTS.md lists no endpoint for
   either (`POST /tables` creates one; nothing reads them, and the only
   profile route, GET /me, answers the gate's question rather than the Me
   tab's). They serve fixtures only. Agree the shape with the team before
   pointing them at a real route. */

/** Open tables near the student. NEEDS AN ENDPOINT. */
export async function listOpenTables({ signal } = {}) {
  if (USE_FIXTURES) return fixtures.openTables
  return request('/tables', { signal })
}

/** Pause or resume matching. The Me tab's switch and the paused banner both
    call it. NEEDS AN ENDPOINT.

    Pausing is a privacy setting the matcher must always respect, so this is
    not a cosmetic toggle: until the route exists, fixture mode is the only
    place it does anything. */
export async function setPaused(paused) {
  if (USE_FIXTURES) {
    const student = readFixtureStudent()
    if (student !== null) writeFixtureStudent({ ...student, paused })
    return { paused }
  }
  return request('/me/paused', { method: 'POST', body: { paused } })
}

/** The Me tab's fuller profile: tags and the private hangout count, which
    GET /me does not carry. NEEDS AN ENDPOINT. */
export async function getMyProfile({ signal } = {}) {
  if (USE_FIXTURES) {
    const student = readFixtureStudent()
    return { ...fixtures.me, ...(student === null ? {} : student) }
  }
  return request('/me/profile', { signal })
}

/* ---------- Fixture-mode profile store ----------
   Without this, fixture mode has to answer GET /me the same way forever, so
   either onboarding or Right now is unreachable and the demo check cannot
   pass with the backend off. Not used once VITE_USE_FIXTURES is false. */

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

/** Hangouts happening now, for the map pins. NEEDS AN ENDPOINT.
    '/hangouts/now' is a provisional path, not an agreed contract.

    Takes no position argument, and must not grow one. There is
    deliberately no parameter through which the student's coordinates could
    reach the backend. The server decides what is public from the group and
    building rows; the phone never tells it where it is. See
    src/lib/useMyLocation.js for the rest of that boundary. */
export async function listHangoutsNow({ signal } = {}) {
  if (USE_FIXTURES) return fixtures.hangoutsNow
  return request('/hangouts/now', { signal })
}

export const usingFixtures = USE_FIXTURES
