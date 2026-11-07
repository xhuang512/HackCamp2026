import { Navigate, Outlet, Route, Routes } from 'react-router-dom'
import TabBar from './components/TabBar.jsx'
import RightNow from './pages/RightNow.jsx'
import MapPage from './pages/MapPage.jsx'
import Me from './pages/Me.jsx'

/* The three-tab shell. One component per screen lives in src/pages/.
   The Projector screen is deliberately outside this shell: it is a
   full-screen stage view with no tab bar. */

function TabShell() {
  return (
    <div className="app">
      <main className="app__screen">
        <Outlet />
        <div className="spacer" />
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
