/* The student's own position, for centring the map and bounding the pan.

   ===================== THE PRIVACY BOUNDARY =====================
   AGENTS.md: "The app uses no live GPS tracking."

   This hook is how that rule is kept while still showing someone where
   they are. Four things enforce it, and all four are load-bearing:

   1. getCurrentPosition, never watchPosition. One fix, taken when asked
      for. A watch is a tracker; a single fix is not. There is no
      navigator.geolocation.watchPosition call anywhere in this repo.

   2. This file imports nothing from api.js and contains no fetch. The
      missing import IS the boundary. Keep it missing.

   3. api.getMap() takes no position argument, not even an
      optional one, so there is no parameter through which a coordinate
      could reach the backend by accident later.

   4. The position is returned to one caller (MapPage), handed to one
      component (CampusMapLive) and drawn as a dot. It is never written to
      localStorage or sessionStorage, never put in the URL, never logged,
      and never attached to a hangout, a table or anything another student
      can see.

   Known and accepted leak, for honesty: requesting map tiles tells the
   tile provider's CDN which tiles are being viewed. Because panning is
   bounded to campus, that reveals "someone is looking at UBC" and nothing
   finer. Self-hosting tiles is the only full fix. Not a blocker.
   ================================================================ */

import { useCallback, useEffect, useRef, useState } from 'react'
import { GEO_MAX_AGE_MS, GEO_TIMEOUT_MS } from './mapConfig.js'

/**
 * @typedef {'idle'|'unsupported'|'insecure'|'prompting'|'ready'|'denied'|'timeout'|'unavailable'} GeoStatus
 */

const OPTIONS = {
  /* Low accuracy on purpose: centring a campus map does not need a
     metre-precise fix, and high accuracy costs battery and GPS warm-up. */
  enableHighAccuracy: false,
  timeout: GEO_TIMEOUT_MS,
  maximumAge: GEO_MAX_AGE_MS,
}

function initialStatus() {
  if (typeof window === 'undefined' || !('geolocation' in navigator)) {
    return 'unsupported'
  }
  /* Geolocation is refused outside a secure context. The common case is a
     phone hitting the dev server at http://192.168.x.x:5173. Detect it
     here so the UI can explain itself instead of silently timing out. */
  if (window.isSecureContext === false) return 'insecure'
  return 'idle'
}

/**
 * @param {{ auto?: boolean }} options `auto` fetches silently when the
 *   browser already reports permission 'granted'. It never triggers the
 *   permission prompt without a user gesture.
 * @returns {{ status: GeoStatus, position: {lat:number,lng:number,accuracy:number}|null, request: () => void }}
 */
export default function useMyLocation({ auto = true } = {}) {
  const [status, setStatus] = useState(initialStatus)
  const [position, setPosition] = useState(null)
  const live = useRef(true)

  useEffect(() => {
    live.current = true
    return () => {
      live.current = false
    }
  }, [])

  const request = useCallback(() => {
    const start = initialStatus()
    if (start !== 'idle') {
      setStatus(start)
      return
    }
    setStatus('prompting')
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        if (!live.current) return
        setPosition({
          lat: coords.latitude,
          lng: coords.longitude,
          accuracy: coords.accuracy,
        })
        setStatus('ready')
      },
      (err) => {
        if (!live.current) return
        if (err.code === err.PERMISSION_DENIED) setStatus('denied')
        else if (err.code === err.TIMEOUT) setStatus('timeout')
        else setStatus('unavailable')
      },
      OPTIONS,
    )
  }, [])

  /* Only fetch on mount when permission is already granted. Otherwise stay
     idle and wait for request() from a real button, so the browser prompt
     stays attached to a user gesture. */
  useEffect(() => {
    if (!auto || initialStatus() !== 'idle') return
    if (!navigator.permissions?.query) return

    let cancelled = false
    navigator.permissions
      .query({ name: 'geolocation' })
      .then(({ state }) => {
        if (!cancelled && state === 'granted') request()
      })
      .catch(() => {
        /* Firefox has historically rejected this query. Staying idle and
           waiting for a tap is the correct fallback. */
      })

    return () => {
      cancelled = true
    }
  }, [auto, request])

  return { status, position, request }
}
