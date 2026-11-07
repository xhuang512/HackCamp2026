import { useAuth } from '../lib/authContext.js'
import Icon from '../components/Icon.jsx'

/* One line about the app and one primary button.
   There is nothing else to decide here, so there is nothing else on screen.

   The email and code screens are Auth0's hosted pages. We do not build them,
   and the designer styles them in the Auth0 dashboard. Code mode, not a
   magic link: a link opens in the mail app's browser, so the session would
   land in a different browser from our installed app. */

export default function Welcome() {
  const { error, canLoginWithEmail, guestAllowed, loginWithUbcEmail, loginAsGuest } =
    useAuth()

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
        {canLoginWithEmail && (
          <button
            type="button"
            className="btn btn--primary btn--xl"
            onClick={loginWithUbcEmail}
          >
            Continue with UBC email
          </button>
        )}

        {/* Demo mode only. First on the stage, because the audience scanning
            the join QR needs the shortest path in. */}
        {guestAllowed && (
          <button
            type="button"
            className={canLoginWithEmail ? 'btn btn--outline btn--lg' : 'btn btn--primary btn--xl'}
            onClick={loginAsGuest}
          >
            Continue as guest
          </button>
        )}

        {!canLoginWithEmail && (
          <p className="welcome__note">
            Email sign-in is off until Auth0 is configured. Set
            VITE_AUTH0_DOMAIN and VITE_AUTH0_CLIENT_ID to turn it on.
          </p>
        )}
      </div>

      <p className="note note--sm">
        <Icon name="lock" size={20} />
        We never store your email address, and nobody else sees your timetable.
      </p>
    </div>
  )
}
