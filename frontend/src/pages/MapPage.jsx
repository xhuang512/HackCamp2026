import { useState } from 'react'
import * as api from '../lib/api.js'
import useAsync from '../lib/useAsync.js'
import ScreenHeader from '../components/ScreenHeader.jsx'
import CampusMap from '../components/CampusMap.jsx'
import OpenTableCard from '../components/OpenTableCard.jsx'
import StateCard from '../components/StateCard.jsx'
import Icon from '../components/Icon.jsx'

/* Campus map plus the open tables anyone can join.
   Public listings carry no names. The map is building level only, from QR
   scans and "on my way" taps, never live GPS. */

export default function MapPage() {
  const [busy, setBusy] = useState(false)
  const { data, error, loading, reload } = useAsync(api.listOpenTables)

  async function join(tableId) {
    setBusy(true)
    try {
      /* No join-a-table endpoint in the contract yet. Raise the shape with
         the team before wiring this to a route. */
      console.warn(`join table ${tableId}: no endpoint yet`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <ScreenHeader eyebrow="Hangout spots near you" title="Campus map" small />

      <div className="map-wrap">
        <CampusMap />
      </div>

      <div className="section">
        <h2 className="section__title">Open tables</h2>

        {loading && <StateCard title="Loading open tables" />}

        {error && (
          <StateCard title="Could not load open tables" onRetry={reload}>
            {error.message}
          </StateCard>
        )}

        {data && data.length === 0 && (
          <StateCard title="No open tables right now">
            Scan a building code to open the first one.
          </StateCard>
        )}

        {data && data.length > 0 && (
          <ul className="rows">
            {data.map((table) => (
              <OpenTableCard key={table.id} table={table} busy={busy} onJoin={join} />
            ))}
          </ul>
        )}

        <p className="note note--sm">
          <Icon name="scan" size={20} />
          At a hangout spot? Scan the building code to check in.
        </p>
      </div>
    </>
  )
}
