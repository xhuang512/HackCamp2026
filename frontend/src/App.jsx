import { useCallback, useState } from 'react'
import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom'
import * as api from './lib/api.js'
import useAsync from './lib/useAsync.js'
import { useAuth } from './lib/authContext.js'
import PausedBanner from './components/PausedBanner.jsx'
import Splash from './components/Splash.jsx'
import StateCard from './components/StateCard.jsx'
import TabBar from './components/TabBar.jsx'
import Aha from './pages/Aha.jsx'
import Me from './pages/Me.jsx'
import MapPage from './pages/MapPage.jsx'
import Onboarding from './pages/Onboarding.jsx'
import Projector from './pages/Projector.jsx'
import RightNow from './pages/RightNow.jsx'
import ScheduleEditor from './pages/ScheduleEditor.jsx'
import Welcome from './pages/Welcome.jsx'

/* The three-tab shell. One component per screen lives in src/pages/.
   The Projector screen is deliberately outside this shell: it is a
   full-screen stage view with no tab bar. */

/* Routes whose screen fills the viewport and does not scroll. The map owns
   its own gestures, so the page must not scroll underneath it. */
const FULL_BLEED = ['/map']

function TabShell({ paused, onResume, resuming }) {
  const { pathname } = useLocation()
  const full = FULL_BLEED.includes(pathname)

  return (
    <div className={full ? 'app app--full' : 'app'}>
      <main className={full ? 'app__screen app__screen--full' : 'app__screen'}>
        {/* Only on Right now, which is the screen pausing actually empties.
            Right now is never full bleed, so the banner and the map layout
            never apply to the same screen. */}
        {paused && pathname === '/' && (
          <PausedBanner onResume={onResume} busy={resuming} />
        )}
        <Outlet />
        {/* A flex-grow spacer next to a full-height map is exactly what
            reintroduces page scroll, so it is omitted there. */}
        {!full && <div className="spacer" />}
      </main>
      <TabBar />
    </div>
  )
}

/* A screen reached from a tab rather than being one. No tab bar, because the
   schedule editor holds unsaved edits and asks before dropping them: with the
   bar on screen, three taps leave without ever reaching that question. Save
   and Back are the way out. */
function PlainShell() {
  return (
    <div className="app">
      <main className="app__screen">
        <Outlet />
        <div className="spacer" />
      </main>
    </div>
  )
}

function Tabs(props) {
  return (
    <Routes>
      <Route element={<TabShell {...props} />}>
        <Route index element={<RightNow />} />
        <Route path="map" element={<MapPage />} />
        <Route path="me" element={<Me />} />
      </Route>
      <Route element={<PlainShell />}>
        <Route path="me/schedule" element={<ScheduleEditor />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

/* ---------- The route gate ----------

   One component decides the first screen of every app open, from three facts:
   is there a session, does the student have a profile, and did they just
   finish onboarding. docs/SIGNUP.md has the full table.

   Two rules are easy to break by accident and worth stating in code:

     Never flash Welcome. While Auth0 restores the session or GET /me is in
     flight we show the splash. A signed-in student who sees a sign-in button
     for one frame reads it as being logged out and taps it.

     A failed GET /me is not a missing profile. Network trouble must show a
     retry, never onboarding, or a student with an account gets asked to make
     a second one and POST /students overwrites the first. */

function Gate() {
  const auth = useAuth()

  /* Unauthenticated opens must not call GET /me at all: there is no token to
     send, so it would 401 and the gate would show a retry screen instead of
     Welcome. */
  const loadMe = useCallback(
    ({ signal }) => (auth.status === 'authed' ? api.getMe({ signal }) : Promise.resolve(null)),
    [auth.status],
  )
  const { data: me, error, loading, reload } = useAsync(loadMe, [auth.status, auth.sub])

  /* The POST /students response, held only until the student taps past the
     aha screen. Holding it here is what makes the aha screen appear exactly
     once per student without a flag in the database: it lives in the memory
     of the one page load that created the profile. */
  const [created, setCreated] = useState(null)

  const [resuming, setResuming] = useState(false)
  const resume = useCallback(async () => {
    setResuming(true)
    try {
      await api.setPaused(false)
      reload()
    } finally {
      setResuming(false)
    }
  }, [reload])

  if (auth.status === 'loading') return <Splash label="Signing you in" />

  /* guestPending is a tapped "Continue as guest" with no token yet: the guest
     token only exists once POST /students returns one. */
  if (auth.status === 'anon' && !auth.guestPending) return <Welcome />

  /* `aha` is null when nobody shares any of their gaps, which the store can
     only report honestly. Showing the screen with a zero on it would undo the
     one job it has, so onboarding goes straight to Right now instead. */
  if (created !== null && created.aha !== null && created.aha !== undefined) {
    return (
      <Aha
        aha={created.aha}
        firstName={created.student?.first_name}
        onContinue={() => setCreated(null)}
      />
    )
  }

  if (loading) return <Splash label="Finding your next gap" />

  if (error !== null) {
    return (
      <div className="app">
        <main className="app__screen">
          <StateCard title="Could not reach your account" onRetry={reload}>
            {error.message}
          </StateCard>
        </main>
      </div>
    )
  }

  if (auth.guestPending || me?.onboarded === false) {
    return (
      <Onboarding
        onDone={(out) => {
          setCreated(out)
          /* Re-ask GET /me behind the aha screen, so Right now has a profile
             the moment they tap through. */
          reload()
        }}
      />
    )
  }

  return (
    <Tabs paused={me?.student?.paused === true} onResume={resume} resuming={resuming} />
  )
}

export default function App() {
  return (
    <Routes>
      {/* Public, and never asks anyone to sign in: it runs on a laptop
          plugged into the stage projector, not on a student's phone. It sits
          outside the gate so no auth state can keep it off screen. */}
      <Route path="/projector" element={<Projector />} />
      <Route path="*" element={<Gate />} />
    </Routes>
  )
}
