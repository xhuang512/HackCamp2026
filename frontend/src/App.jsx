import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom'
import TabBar from './components/TabBar.jsx'
import RightNow from './pages/RightNow.jsx'
import MapPage from './pages/MapPage.jsx'
import Me from './pages/Me.jsx'

/* The three-tab shell. One component per screen lives in src/pages/.
   The Projector screen is deliberately outside this shell: it is a
   full-screen stage view with no tab bar. */

/* Routes whose screen fills the viewport and does not scroll. The map owns
   its own gestures, so the page must not scroll underneath it. */
const FULL_BLEED = ['/map']

function TabShell() {
  const { pathname } = useLocation()
  const full = FULL_BLEED.includes(pathname)

  return (
    <div className={full ? 'app app--full' : 'app'}>
      <main className={full ? 'app__screen app__screen--full' : 'app__screen'}>
        <Outlet />
        {/* A flex-grow spacer next to a full-height map is exactly what
            reintroduces page scroll, so it is omitted there. */}
        {!full && <div className="spacer" />}
      </main>
      <TabBar />
    </div>
  )
}

export default function App() {
  return (
    <Routes>
      <Route element={<TabShell />}>
        <Route index element={<RightNow />} />
        <Route path="map" element={<MapPage />} />
        <Route path="me" element={<Me />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
