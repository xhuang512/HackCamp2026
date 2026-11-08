/* Map constants and tile sources. No React, no DOM, no network.
   This is the one file to edit when the real coordinates arrive.

   ============================ READ THIS ============================
   Coordinates are checked against OpenStreetMap building centroids and UBC
   location pages. Keep the seeded buildings and fixtures in sync with these.

   The eventual source of truth is the `buildings` table in
   backend/schema.sql (lat, lng, slug, name), seeded by backend/seed.py,
   which is still empty. Once that exists, these values go away.
   =================================================================== */

/** Roughly the middle of UBC Vancouver's academic core. */
export const CAMPUS_CENTER = { lat: 49.2606, lng: -123.246 }

/* How far the user may pan from their position, in metres.
   1200 m because UBC's academic core is roughly 1.2 km across, so from
   anywhere inside it every meetable building stays reachable, while
   downtown Vancouver does not. Raise it for a wider demo, lower it to
   make the map feel more strictly "campus only". */
export const PAN_RADIUS_M = 1200

/* Beyond this distance from CAMPUS_CENTER we treat the student as off
   campus and keep the view on campus instead. Bounding a 1.2 km circle
   around someone at home would hide every pin. */
export const OFF_CAMPUS_M = 3000

export const DEFAULT_ZOOM = 16
export const MAX_ZOOM = 18

/* Geolocation. A single fix, so these are the only knobs. */
export const GEO_TIMEOUT_MS = 8000
export const GEO_MAX_AGE_MS = 60000

/* ---------------------------- TILES ----------------------------

   CARTO was the first choice and it does NOT work. Its CDN answers an
   unauthenticated request with HTTP 200, content-type image/png, and a
   256x256 watermark reading "API KEY REQUIRED". A status-code check
   passes; the map just shows grey boxes with text on them. Verified by
   downloading a tile and looking at it.

   So there are two providers here:

   - OpenStreetMap is the default. No key, no sign-up, works on localhost
     and on any deployed domain. Light only: there is no official dark
     OSM raster style.

   - Stadia Maps is the upgrade, and the only reason to bother is dark
     mode. Alidade Smooth and Alidade Smooth Dark are a matched light/dark
     pair in the muted style this app is drawn in, with real 512px retina
     tiles. Verified: localhost is served with no key, a deployed domain
     without a key gets HTTP 401.

   That 401 is the trap. Stadia works all through local development and
   then breaks the moment the app is deployed, which for this project
   means on stage. Set VITE_STADIA_API_KEY before deploying, or stay on
   OSM. docs/MAP-TILES.md is the walkthrough.                            */

const STADIA_KEY = import.meta.env.VITE_STADIA_API_KEY ?? ''

const LOCAL_HOSTS = ['localhost', '127.0.0.1', '[::1]', '0.0.0.0']

/** Stadia needs a key everywhere except localhost. */
function stadiaUsable() {
  if (STADIA_KEY) return true
  if (typeof window === 'undefined') return false
  return LOCAL_HOSTS.includes(window.location.hostname)
}

const OSM_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'

const STADIA_ATTRIBUTION =
  '&copy; <a href="https://stadiamaps.com/" target="_blank">Stadia Maps</a> ' +
  '&copy; <a href="https://openmaptiles.org/" target="_blank">OpenMapTiles</a> ' +
  OSM_ATTRIBUTION

const OSM = {
  url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  attribution: OSM_ATTRIBUTION,
  maxZoom: 19,
}

function stadia(style) {
  const key = STADIA_KEY ? `?api_key=${STADIA_KEY}` : ''
  return {
    url: `https://tiles.stadiamaps.com/tiles/${style}/{z}/{x}/{y}{r}.png${key}`,
    attribution: STADIA_ATTRIBUTION,
    maxZoom: 20,
  }
}

/**
 * The tile layer for a colour scheme.
 * @param {'light'|'dark'} scheme
 * @returns {{ url: string, attribution: string, maxZoom: number, subdomains?: string }}
 */
export function tileSource(scheme) {
  if (!stadiaUsable()) {
    /* OSM has no dark style, so a dark-mode viewer gets the light map.
       Readable, just brighter than the rest of the UI. A Stadia key fixes
       it. */
    return OSM
  }
  return stadia(scheme === 'dark' ? 'alidade_smooth_dark' : 'alidade_smooth')
}

/** True when the map is on the no-key fallback, so the UI can say so. */
export const usingFallbackTiles = !stadiaUsable()

/** Metres between two { lat, lng } points. Haversine, good enough at
    campus scale. Used only to decide "is this fix on campus", never sent
    anywhere. */
export function metresBetween(a, b) {
  const R = 6371000
  const toRad = (d) => (d * Math.PI) / 180
  const dLat = toRad(b.lat - a.lat)
  const dLng = toRad(b.lng - a.lng)
  const lat1 = toRad(a.lat)
  const lat2 = toRad(b.lat)
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(h))
}
