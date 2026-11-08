import * as api from '../lib/api.js'
import useAsync from '../lib/useAsync.js'

/* The stage screen, on a laptop plugged into the projector.

   A PLACEHOLDER. Tier 1 item 4 is the real one, where anonymous dots cluster
   into groups live off Supabase realtime. This exists because the route gate
   has to prove one thing today: /projector renders without a session, from a
   browser nobody has signed into. Whoever builds the clustering view owns
   this file and should replace the body, not work around it.

   Nothing here is per-student. The counts are the only public numbers in the
   app, and a count is not a name. */

export default function Projector() {
  const { data, error } = useAsync(api.getProjector)

  return (
    <div className="stage on-dark">
      <span className="stage__label">Hangout, live at UBC</span>

      {error !== null && <p className="stage__note">Waiting for the server.</p>}

      {data !== null && (
        <>
          <p className="stage__number">{data.joined}</p>
          <p className="stage__caption">hangouts that actually happened</p>
          <p className="stage__note">
            {data.groups} groups out right now
          </p>
        </>
      )}
    </div>
  )
}
