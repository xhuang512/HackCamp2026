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

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
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

async function request(path, { method = 'GET', body, signal } = {}) {
  const token = getSession()
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

/** POST /students — sign up with a preset schedule, tags and first name. */
export async function signUp({ first_name, tags, schedule_id }) {
  if (USE_FIXTURES) return { session: 'fixture-session' }
  const out = await request('/students', {
    method: 'POST',
    body: { first_name, tags, schedule_id },
  })
  if (out?.session) setSession(out.session)
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

/** GET /health — the one endpoint that exists today. */
export async function getHealth({ signal } = {}) {
  return request('/health', { signal })
}

/* ---------- Not in the contract yet ----------
   The Map and Me screens need these, but AGENTS.md lists no endpoint for
   either (`POST /tables` creates one; nothing reads them, and there is no
   profile endpoint). They serve fixtures only. Agree the shape with the team
   before pointing them at a real route. */

/** Open tables near the student. NEEDS AN ENDPOINT. */
export async function listOpenTables({ signal } = {}) {
  if (USE_FIXTURES) return fixtures.openTables
  return request('/tables', { signal })
}

/** The signed-in student's own profile. NEEDS AN ENDPOINT. */
export async function getMe({ signal } = {}) {
  if (USE_FIXTURES) return fixtures.me
  return request('/me', { signal })
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
