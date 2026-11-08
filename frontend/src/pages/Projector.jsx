import * as api from '../lib/api.js'
import useAsync from '../lib/useAsync.js'

/* The stage screen, on a laptop plugged into the projector.

   Nothing here is per-student. The counts are the only public numbers in the
   app, and a count is not a name. */

export default function Projector() {
  const { data, error, loading, reload } = useAsync(api.getProjector)

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
