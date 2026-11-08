import * as api from '../lib/api.js'
import useAsync from '../lib/useAsync.js'
import { useAuth } from '../lib/authContext.js'
import Icon from '../components/Icon.jsx'

/* One line about the app and one primary button.
   There is nothing else to decide here, so there is nothing else on screen.

   Google sign-in is Auth0's hosted flow. UBC-only email is deliberately
   paused; docs/SIGNUP.md forbids claiming these are verified accounts. */

export default function Welcome() {
  const { error, canLoginWithGoogle, guestAllowed, loginWithGoogle, loginAsGuest } =
    useAuth()

  /* guestAllowed is the frontend's own VITE_DEMO_MODE. The backend decides
     whether a guest token is actually issued, and the two disagree whenever
     only one of them is set: the button appears, the student taps it, and
     POST /students refuses with nothing on screen to explain why.
     GET /auth/config is the authoritative answer and needs no session.

     Only a definite `false` says anything. A backend that is down or
     unreachable leaves this silent, because the job of this screen is to get
     people in and a failed sign-in reports itself. */
  const config = useAsync(api.getAuthConfig)
  const guestsRefused = guestAllowed && config.data?.demo_mode === false

  return (
    <div className="welcome">
      <div className="welcome__top">
        <span className="welcome__name">Hangout</span>
        <h1 className="welcome__pitch">
          Find someone to hang out with in your next gap between classes.
        </h1>
        <p className="welcome__sub">
          Add your timetable once. Before each gap we suggest one small group
          and a place on campus to meet.
        </p>
      </div>

      {/* A denied login is the one error a student can act on, so it sits
          directly above the button they will press again. role="alert" because
          it appears after the redirect, not on first paint. */}
      {error !== null && (
        <p className="welcome__error" role="alert">
          {error}
        </p>
      )}

      <div className="welcome__actions">
        {canLoginWithGoogle && (
          <button
            type="button"
            className="btn btn--primary btn--xl"
            onClick={loginWithGoogle}
          >
            Continue with Google
          </button>
        )}

        {/* Demo mode only. First on the stage, because the audience scanning
            the join QR needs the shortest path in. */}
        {guestAllowed && (
          <button
            type="button"
            className={canLoginWithGoogle ? 'btn btn--outline btn--lg' : 'btn btn--primary btn--xl'}
            onClick={loginAsGuest}
            disabled={guestsRefused}
          >
            Continue as guest
          </button>
        )}

        {guestsRefused && (
          <p className="welcome__note" role="status">
            Guest sign-in is off on the server. Set DEMO_MODE=true in the
            backend&apos;s .env and restart it.
          </p>
        )}

        {!canLoginWithGoogle && (
          <p className="welcome__note">
            Google sign-in is off until Auth0 is configured. Set
            VITE_AUTH0_DOMAIN and VITE_AUTH0_CLIENT_ID to turn it on.
          </p>
        )}
      </div>

      <p className="note note--sm">
        <Icon name="lock" size={20} />
        Guest profiles are unverified. We never store your email address, and nobody else sees your timetable.
      </p>
    </div>
  )
}
