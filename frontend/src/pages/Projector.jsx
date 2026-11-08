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

  return (
    <div className="stage on-dark">
      <span className="stage__label">Hangout, live at UBC</span>

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
    </div>
  )
}
