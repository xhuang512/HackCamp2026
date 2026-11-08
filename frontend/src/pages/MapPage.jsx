import { Suspense, lazy, useMemo, useRef, useState } from 'react'
import * as api from '../lib/api.js'
import useAsync from '../lib/useAsync.js'
import { MAP_POLL_MS } from '../lib/live.js'
import useColorScheme from '../lib/useColorScheme.js'
import useMyLocation from '../lib/useMyLocation.js'
import { CAMPUS_CENTER, OFF_CAMPUS_M, metresBetween } from '../lib/mapConfig.js'
import { placeLabel, placeMeta, placesFrom } from '../lib/hangouts.js'
import CampusMap from '../components/CampusMap.jsx'
import MapBoundary from '../components/MapBoundary.jsx'
import StateCard from '../components/StateCard.jsx'

/* The campus map and what is happening on it right now.

   Privacy: public listings carry no names. A pin shows a place and a count,
   and GET /map omits any building with fewer than three students rather than
   sending a number somebody could be singled out by. The viewer's own
   position is used only to centre the map and bound the panning, and is
   never sent anywhere. See src/lib/useMyLocation.js.

   Leaflet is loaded lazily and only when there is a DOM, because it reads
   window and document at module scope. */

const CampusMapLive = lazy(() => import('../components/CampusMapLive.jsx'))

const canUseDOM =
  typeof window !== 'undefined' && typeof document !== 'undefined'

/* What each geolocation state says on screen. `null` means say nothing:
   the map is already centred and there is no problem to explain. */
function locationNotice(status, request) {
  switch (status) {
    case 'prompting':
      return { title: 'Finding you' }
    case 'denied':
      return {
        title: 'Location is off',
        body: 'Showing campus instead. Turn location on for this site in your browser settings to centre the map on you.',
        /* No retry: after a hard deny, a second request is a no-op in
           Chrome, so a button that does nothing would look broken. */
      }
    case 'insecure':
      return {
        title: 'Location needs HTTPS',
        body: 'Browsers only share location over a secure connection. On a phone, open the site through an HTTPS tunnel rather than the local network address.',
      }
    case 'unsupported':
      return {
        title: 'Location is unavailable',
        body: 'This browser does not support location. Showing campus instead.',
      }
    case 'timeout':
      return {
        title: 'Location took too long',
        body: 'Showing campus instead.',
        onRetry: request,
      }
    case 'unavailable':
      return {
        title: 'Could not get your location',
        body: 'Showing campus instead.',
        onRetry: request,
      }
    default:
      return null
  }
}

export default function MapPage() {
  const { status, position, request } = useMyLocation()
  const scheme = useColorScheme()
  /* Polled so a groupmate's check-in reaches the map without a reload.
     Slower than the projector: building activity moves slowly and this
     one runs on a phone. */
  const { data, error, loading, stale, reload } = useAsync(api.getMap, [], {
    pollMs: MAP_POLL_MS,
  })
  const mapRef = useRef(null)
  const [focus, setFocus] = useState(null)

  const places = useMemo(() => placesFrom(data), [data])
  const myGroup = data?.my_group ?? null

  /* A fix from off campus would bound a 1.2km circle around someone's
     house and hide every pin, so the view stays on campus instead. */
  const offCampus =
    position !== null &&
    metresBetween(position, CAMPUS_CENTER) > OFF_CAMPUS_M
  const centreOn = offCampus ? null : position

  const notice = locationNotice(status, request)
  /* The static SVG is the honest answer when there will never be a fix. */
  const useFallback = !canUseDOM

  function show(id) {
    /* A counter, not Date.now(): the nonce only needs to change so that
       tapping the same row twice flies to it again. */
    setFocus((prev) => ({ id, nonce: (prev?.nonce ?? 0) + 1 }))
    mapRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  return (
    <>
      <header className="rd-head">
        <h1 className="rd-title">Campus map</h1>
      </header>
      <p className="rd-sub rd-sub--sm">
        {offCampus
          ? "You're not on campus right now"
          : myGroup
            ? `Your group is at ${myGroup.name}`
            : `Hangouts happening now · ${places.length} on the map`}
      </p>

      {/* The redesign draws a rounded map block with the building list under
          it. The real Leaflet map sits in that block, and the list below is
          also the keyboard and screen-reader path to the pins. */}
      <div className="rd-map" ref={mapRef}>
        {useFallback ? (
          <CampusMap full />
        ) : (
          <MapBoundary>
            <Suspense fallback={<div className="map-live" />}>
              <CampusMapLive
                position={centreOn}
                places={places}
                scheme={scheme}
                focus={focus}
              />
            </Suspense>
          </MapBoundary>
        )}
      </div>

      <div className="rd-notices">
        {status === 'idle' && (
          <button type="button" className="btn btn--ghost" onClick={request}>
            Use my location
          </button>
        )}
        {notice && (
          <StateCard title={notice.title} onRetry={notice.onRetry}>
            {notice.body}
          </StateCard>
        )}
        {error && (
          <StateCard title="Could not load the map" onRetry={reload}>
            {error.message}
          </StateCard>
        )}
        {myGroup && (
          <p className="rd-status" role="status">
            {myGroup.state === 'active' ? 'Meeting now' : 'Confirmed'} ·{' '}
            {myGroup.checked_in_count} of {myGroup.joined_count} checked in at {myGroup.name}
            {/* The count is the thing being polled, so if a refresh fails
                the number beside it has to stop claiming to be current. */}
            {stale && <span className="map-group-status__stale"> · reconnecting</span>}
          </p>
        )}
      </div>

      <section className="rd-block" aria-labelledby="browse-title">
        <h2 className="rd-h2" id="browse-title">Browse buildings</h2>
        {loading && <p className="row__meta">Loading the map…</p>}
        {places.length === 0 && !loading ? (
          <p className="row__meta">
            Quiet on campus right now. Start a group from the Groups tab
            and yours will be the first one here.
          </p>
        ) : (
          <ul className="pin-list" id="place-list">
            {places.map((place) => (
              <li key={place.id}>
                <button
                  type="button"
                  className="pin-list__btn"
                  onClick={() => show(place.id)}
                  aria-label={`Show on map: ${placeLabel(place)}`}
                >
                  <span className="pin-list__text">
                    <span className="pin-list__name">{place.name} <span aria-hidden="true">›</span></span>
                    <span className="pin-list__meta">{placeMeta(place)}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  )
}
