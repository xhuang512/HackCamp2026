/* The one place the app asks "who is this, and do we have a token for them?"
   Everything else calls useAuth() from ./authContext.js. Swapping the
   mechanism behind it is a one-file change, which is the point: Auth0 is a
   tier 2 item, the demo needs a way in today, and no screen should have to
   know which one is running.

   Two implementations, chosen once at module load from the env, so the hook
   order never changes between renders:

     Auth0Bridge        VITE_AUTH0_DOMAIN and VITE_AUTH0_CLIENT_ID are set.
                        Google sign-in through Auth0.
     GuestOnlyProvider  They are not. Guests only, which is what a fresh
                        clone and the stage demo both get.

   We never see or store the email address. Auth0 keeps it; the backend stores
   only Auth0's `sub` in students.auth_sub. The only identifier that reaches
   this file is that opaque sub. */

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Auth0Provider, useAuth0 } from '@auth0/auth0-react'
import * as api from './api.js'
import {
  AuthContext,
  EMPTY,
  auth0Config,
  auth0Configured,
  guestAllowed,
} from './authContext.js'

export function AuthProvider({ children }) {
  if (!auth0Configured) return <GuestOnlyProvider>{children}</GuestOnlyProvider>

  return (
    <Auth0Provider
      domain={auth0Config.domain}
      clientId={auth0Config.clientId}
      authorizationParams={{
        redirect_uri: window.location.origin,
        ...(auth0Config.audience === undefined
          ? {}
          : { audience: auth0Config.audience }),
      }}
      /* localStorage plus refresh tokens is what keeps iPhone Safari signed
         in. Safari's storage partitioning evicts Auth0's in-memory default
         and the silent-auth iframe, so a student would see login every open. */
      cacheLocation="localstorage"
      useRefreshTokens
    >
      <Auth0Bridge>{children}</Auth0Bridge>
    </Auth0Provider>
  )
}

/* ---------- Guests only ---------- */

function GuestOnlyProvider({ children }) {
  const [token, setToken] = useState(() => api.getSession())
  const [guestPending, setGuestPending] = useState(false)

  useEffect(() => {
    const expired = () => {
      setGuestPending(false)
      setToken(null)
    }
    window.addEventListener(api.SESSION_EXPIRED_EVENT, expired)
    return () => window.removeEventListener(api.SESSION_EXPIRED_EVENT, expired)
  }, [])

  const value = useMemo(
    () => ({
      ...EMPTY,
      status: token === null ? 'anon' : 'authed',
      kind: token === null ? null : 'guest',
      sub: token === null ? null : 'guest',
      guestPending,
      canLoginWithGoogle: false,
      guestAllowed: true,
      loginWithGoogle: () => {},
      loginAsGuest: () => setGuestPending(true),
      /* Called by the last onboarding step once POST /students hands back a
         guest token. api.js has already stored it; this picks it up. */
      adoptGuestToken: () => {
        setGuestPending(false)
        setToken(api.getSession())
      },
      logout: () => {
        api.setSession(null)
        api.clearFixtureStudent()
        setGuestPending(false)
        setToken(null)
      },
    }),
    [token, guestPending],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

/* ---------- Auth0 ---------- */

function Auth0Bridge({ children }) {
  const {
    isLoading,
    isAuthenticated,
    user,
    error,
    loginWithRedirect,
    logout: auth0Logout,
    getAccessTokenSilently,
  } = useAuth0()

  const [guestPending, setGuestPending] = useState(false)
  /* A refresh token that will not exchange is a dead session. SIGNUP.md:
     treat it as no session and show Welcome, rather than leaving the student
     on a screen whose every request 401s. */
  const [tokenDead, setTokenDead] = useState(false)
  const [guestToken, setGuestToken] = useState(() => api.getSession())

  useEffect(() => {
    const expired = () => {
      setGuestPending(false)
      setGuestToken(null)
    }
    window.addEventListener(api.SESSION_EXPIRED_EVENT, expired)
    return () => window.removeEventListener(api.SESSION_EXPIRED_EVENT, expired)
  }, [])

  /* api.js stays the only file that calls the backend, so it cannot import
     a React hook to get the token. It asks for one instead. */
  useEffect(() => {
    api.setTokenProvider(async () => {
      if (!isAuthenticated) return null
      try {
        return await getAccessTokenSilently()
      } catch {
        setTokenDead(true)
        return null
      }
    })
    return () => api.setTokenProvider(null)
  }, [isAuthenticated, getAccessTokenSilently])

  const logout = useCallback(() => {
    api.setSession(null)
    api.clearFixtureStudent()
    setGuestToken(null)
    setGuestPending(false)
    if (isAuthenticated) {
      auth0Logout({ logoutParams: { returnTo: window.location.origin } })
    }
  }, [auth0Logout, isAuthenticated])

  const value = useMemo(() => {
    const live = isAuthenticated && !tokenDead
    const status = isLoading ? 'loading' : live || guestToken !== null ? 'authed' : 'anon'

    return {
      status,
      kind: live ? 'auth0' : guestToken === null ? null : 'guest',
      sub: live ? (user?.sub ?? null) : guestToken === null ? null : 'guest',
      error: messageFor(error),
      guestPending,
      canLoginWithGoogle: true,
      guestAllowed,
      loginWithGoogle: () =>
        loginWithRedirect({ authorizationParams: { connection: 'google-oauth2' } }),
      loginAsGuest: () => setGuestPending(true),
      adoptGuestToken: () => {
        setGuestPending(false)
        setGuestToken(api.getSession())
      },
      logout,
    }
  }, [
    isLoading,
    isAuthenticated,
    tokenDead,
    guestToken,
    guestPending,
    user,
    error,
    loginWithRedirect,
    logout,
  ])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

function messageFor(error) {
  if (!error) return null
  if (error.error === 'access_denied') {
    return error.message || 'Sign in was cancelled. Please try again.'
  }
  return error.message || 'Sign in did not finish. Please try again.'
}
