/* Who the signed-in student is, as seen by every screen.

   Split from auth.jsx only because a module that exports a React component
   cannot also export hooks and constants without breaking Vite's fast
   refresh. auth.jsx holds the provider; this holds the shape it provides.

   We never see or store the email address. Auth0 keeps it, and the backend
   stores only Auth0's opaque `sub` in students.auth_sub. That sub is the only
   identifier that reaches the frontend. */

import { createContext, useContext } from 'react'

const DOMAIN = import.meta.env.VITE_AUTH0_DOMAIN
const CLIENT_ID = import.meta.env.VITE_AUTH0_CLIENT_ID
const AUDIENCE = import.meta.env.VITE_AUTH0_AUDIENCE

export const auth0Config = { domain: DOMAIN, clientId: CLIENT_ID, audience: AUDIENCE }

/** Is there an Auth0 tenant to talk to? Read once at module load, so the
    provider's choice of implementation never changes between renders and the
    hook order stays stable. */
export const auth0Configured = Boolean(DOMAIN && CLIENT_ID)

/* DEMO_MODE's frontend half. It only adds the guest button; the backend
   decides whether a guest token is actually issued, and refuses `guest: true`
   when its own DEMO_MODE is off. Forced on without Auth0, because otherwise
   there is no way into the app at all. */
export const guestAllowed =
  import.meta.env.VITE_DEMO_MODE === 'true' || !auth0Configured

export const AuthContext = createContext(null)

/* status
     'loading'  Auth0 is restoring a session. Show the splash, never Welcome.
     'anon'     No session. Welcome.
     'authed'   We have a token. `sub` identifies the student.

   `guestPending` remains for compatibility with an in-flight legacy guest
   flow. New guests receive a short-lived onboarding token before the first
   screen so authenticated schedule parsing works before their profile exists. */
export const EMPTY = {
  status: 'anon',
  kind: null,
  sub: null,
  error: null,
  guestPending: false,
}

export function useAuth() {
  const value = useContext(AuthContext)
  if (value === null) throw new Error('useAuth() outside <AuthProvider>')
  return value
}

/** The key the onboarding draft is filed under. One draft per identity. */
export function draftKeyFor(auth) {
  if (auth.kind === 'auth0' && auth.sub !== null) return auth.sub
  return 'guest'
}
