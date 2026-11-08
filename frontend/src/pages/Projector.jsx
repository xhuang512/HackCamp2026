import { useCallback, useState } from 'react'
import * as api from '../lib/api.js'
import useAsync from '../lib/useAsync.js'
import { PROJECTOR_POLL_MS } from '../lib/live.js'

/* The stage screen, on a laptop plugged into the projector.

   Nothing here is per-student. The counts are the only public numbers in the
   app, and a count is not a name.

   It refetches on a timer, because the demo turns on these numbers moving:
   two phones check each other in and the checked-in count goes up while the
   room watches. It used to fetch once per page load and then sit frozen,
   which meant reloading the laptop by hand at the right second. useLive in
   src/lib/live.js is where this goes once Supabase realtime is wired up. */

export default function Projector() {
  const { data, error, loading, stale, reload } = useAsync(api.getProjector, [], {
    pollMs: PROJECTOR_POLL_MS,
  })

  /* Step 6 of the AGENTS.md demo check is POST /admin/reset restoring the
     seed data, and there was no way to do it from the app. It belongs here
     rather than on a student's phone: this screen is the laptop the person
     running the demo is already standing at, and the route is public so it
     needs no session.

     Gated on the backend's own demo_mode, not on VITE_DEMO_MODE, because the
     endpoint is refused outright when the server's DEMO_MODE is off. Asking
     first means the button is absent rather than present and broken. */
  const config = useAsync(api.getAuthConfig)
  const resettable = config.data?.demo_mode === true

  const [resetting, setResetting] = useState(false)
  const [resetError, setResetError] = useState(null)

  const reseed = useCallback(async () => {
    /* A reseed deletes the seed students and their groups. Harmless, and
       still worth one tap of confirmation on a machine wired to a projector
       in front of a room. */
    if (!window.confirm('Reseed the demo data? This clears the seeded groups and check-ins.')) return
    setResetting(true)
    setResetError(null)
    try {
      await api.adminReset()
      reload()
    } catch (err) {
      setResetError(err)
    } finally {
      setResetting(false)
    }
  }, [reload])

  return (
    <div className="stage on-dark">
      <span className="stage__label">UBC Meet, live at UBC</span>

      {loading && <p className="stage__note">Connecting to the room…</p>}
      {error !== null && (
        <div className="stage__error">
          <p className="stage__note">Waiting for the server.</p>
          <button type="button" className="btn btn--ghost" onClick={reload}>Try again</button>
        </div>
      )}

      {data !== null && (
        <>
          <p className="stage__number">{data.checked_in}</p>
          <p className="stage__caption">students checked in together</p>
          <div className="stage__counts" aria-label="Live group totals">
            <span><strong>{data.forming}</strong> forming</span>
            <span><strong>{data.confirmed}</strong> confirmed</span>
            <span><strong>{data.students}</strong> participating</span>
          </div>
          {/* A failed refresh keeps the last good numbers rather than
              blanking the stage, so it has to admit they are old. */}
          {stale && (
            <p className="stage__note" role="status">
              Reconnecting. These numbers may be a moment behind.
            </p>
          )}
          {data.dots.length === 0 ? (
            <p className="stage__note">Groups will appear here as students join.</p>
          ) : (
            <ul className="stage__dots" aria-label="Anonymous activity by building">
              {data.dots.map((dot) => (
                <li key={dot.slug}>
                  <span className="stage__dot" aria-hidden="true" />
                  {dot.name}: {dot.count}
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      {resettable && (
        <div className="stage__admin">
          <button
            type="button"
            className="btn btn--ghost"
            onClick={reseed}
            disabled={resetting}
          >
            {resetting ? 'Reseeding…' : 'Reset demo data'}
          </button>
          {resetError !== null && (
            <p className="stage__note" role="alert">{resetError.message}</p>
          )}
        </div>
      )}
    </div>
  )
}
