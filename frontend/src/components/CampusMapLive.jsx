/* The real map. This is the ONLY module that imports Leaflet, and it is
   loaded lazily by MapPage so that:
     - leaflet's ~150kB and leaflet.css ride in a separate chunk
     - nothing touches window/document until there is a DOM

   Leaflet reads window, document and navigator at module scope, so a
   static import of this file anywhere up the tree would break any
   server-side render. MapPage guards it with canUseDOM plus React.lazy.

   leaflet.css is imported here rather than in index.css so the stylesheet
   lands in the lazy chunk too. */

import L from 'leaflet'
import { useEffect, useMemo, useRef } from 'react'
import {
  Circle,
  CircleMarker,
  MapContainer,
  Marker,
  Popup,
  TileLayer,
  ZoomControl,
  useMap,
} from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import {
  CAMPUS_CENTER,
  DEFAULT_ZOOM,
  MAX_ZOOM,
  PAN_RADIUS_M,
  tileSource,
} from '../lib/mapConfig.js'
import { hangoutLabel } from '../lib/hangouts.js'

/* Keeps panning inside a circle around `center`.

   maxBounds alone is not enough: with no minZoom the viewer zooms out
   until the bounded box is smaller than the viewport, at which point
   Leaflet stops enforcing anything and the whole world is reachable.
   getBoundsZoom derives that floor from the real viewport, so it is
   correct at 390px and on a tablet. */
function PanLimit({ center, radiusM }) {
  const map = useMap()
  const userMoved = useRef(false)
  /* Leaflet has setMaxBounds but no getMaxBounds, so the previous bounds
     are tracked here rather than read back off the map. */
  const prevBounds = useRef(null)

  useEffect(() => {
    const onDrag = () => {
      userMoved.current = true
    }
    map.on('dragstart', onDrag)
    return () => {
      map.off('dragstart', onDrag)
    }
  }, [map])

  useEffect(() => {
    /* toBounds takes a DIAMETER, not a radius. */
    const bounds = L.latLng(center.lat, center.lng).toBounds(radiusM * 2)
    const previous = prevBounds.current

    map.setMaxBounds(bounds)

    /* The zoom floor has to be derived from the viewport, so it is wrong
       until the container has a size, and it changes when the container
       resizes. Recompute on both. */
    const applyMinZoom = () => {
      if (map.getSize().y === 0) return
      const floor = map.getBoundsZoom(bounds)
      if (Number.isFinite(floor)) map.setMinZoom(Math.ceil(floor))
    }
    applyMinZoom()
    map.on('resize', applyMinZoom)

    /* Re-centre on a fix only if the viewer has not started panning, or if
       the new position falls outside the bounds already in use. Otherwise
       a slow GPS result yanks the view out from under someone mid-drag. */
    const outside = previous !== null && !previous.contains([center.lat, center.lng])
    if (!userMoved.current || outside) {
      map.setView([center.lat, center.lng], map.getZoom(), { animate: false })
    }
    map.panInsideBounds(bounds, { animate: false })
    prevBounds.current = bounds

    return () => {
      map.off('resize', applyMinZoom)
    }
  }, [map, center.lat, center.lng, radiusM])

  return null
}

/* Leaflet caches the container size on init. 100dvh changes as iOS
   Safari's toolbars collapse, and a map measured at the wrong size keeps
   grey gutters forever. */
function KeepSized() {
  const map = useMap()

  useEffect(() => {
    const resize = () => map.invalidateSize()
    /* Once after mount, for the case where the container was still being
       laid out when Leaflet measured it. */
    const id = setTimeout(resize, 0)

    window.addEventListener('resize', resize)
    window.addEventListener('orientationchange', resize)
    window.visualViewport?.addEventListener('resize', resize)

    return () => {
      clearTimeout(id)
      window.removeEventListener('resize', resize)
      window.removeEventListener('orientationchange', resize)
      window.visualViewport?.removeEventListener('resize', resize)
    }
  }, [map])

  return null
}

/* Where the viewer is: a dot plus the accuracy radius. Not interactive and
   not announced, because a decorative dot that speaks on every focus move
   is noise. The page text says whether the location is in use. */
function MeMarker({ position }) {
  return (
    <>
      <Circle
        center={[position.lat, position.lng]}
        radius={position.accuracy}
        interactive={false}
        pathOptions={{
          className: 'me-halo',
          stroke: false,
          fillOpacity: 0.15,
        }}
      />
      <CircleMarker
        center={[position.lat, position.lng]}
        radius={8}
        interactive={false}
        pathOptions={{ className: 'me-dot', weight: 3, fillOpacity: 1 }}
      />
    </>
  )
}

/* One pin per hangout.

   Leaflet divIcons are plain divs, so the accessible name and role are set
   through the marker element in an effect: Leaflet's own `alt` option only
   applies to image icons. The label carries a mode, a place, a count and a
   time, and never a name. */
function HangoutPin({ hangout, registry }) {
  const markerRef = useRef(null)
  const label = hangoutLabel(hangout)

  const icon = useMemo(
    () =>
      L.divIcon({
        className: '',
        html:
          `<span class="pin pin--${hangout.mode}">` +
          (hangout.mode === 'study'
            ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H10a2 2 0 0 1 2 2v13a1.5 1.5 0 0 0-1.5-1.5H5.5A1.5 1.5 0 0 1 4 16V5.5z"/><path d="M20 5.5A1.5 1.5 0 0 0 18.5 4H14a2 2 0 0 0-2 2v13a1.5 1.5 0 0 1 1.5-1.5h5A1.5 1.5 0 0 0 20 16V5.5z"/></svg>'
            : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="9" cy="8.5" r="2.8"/><path d="M3.5 19c.9-2.8 3-4.2 5.5-4.2s4.6 1.4 5.5 4.2"/><path d="M16 6.2a2.8 2.8 0 0 1 0 5.3M18 14.4c1.6.6 2.7 1.8 3.3 3.4"/></svg>'),
        iconSize: [44, 44],
        /* Anchor at the bottom centre so the pin points at the building. */
        iconAnchor: [22, 44],
        popupAnchor: [0, -44],
      }),
    [hangout.mode],
  )

  useEffect(() => {
    const el = markerRef.current?.getElement()
    if (!el) return
    /* Leaflet's own `alt` option only applies to image icons, so the role
       and name go on the element directly. */
    el.setAttribute('role', 'button')
    el.setAttribute('aria-label', label)
  }, [label])

  /* Let FocusHangout open this marker's popup by id. */
  useEffect(() => {
    if (!registry) return undefined
    registry.set(hangout.id, markerRef)
    return () => {
      registry.delete(hangout.id)
    }
  }, [registry, hangout.id])

  return (
    <Marker
      ref={markerRef}
      position={[hangout.building.lat, hangout.building.lng]}
      icon={icon}
      keyboard
    >
      <Popup>
        <strong>{hangout.building.name}</strong>
        <br />
        {label}
      </Popup>
    </Marker>
  )
}

/* Flies to one hangout and opens its popup when `focus` changes.

   Driven by a plain prop so MapPage never holds a Leaflet ref: everything
   Leaflet-shaped stays inside this lazily loaded module. `focus.nonce`
   makes a repeat tap on the same row fly again. */
function FocusHangout({ focus, hangouts, registry }) {
  const map = useMap()

  useEffect(() => {
    if (!focus?.id) return
    const hangout = hangouts.find((h) => h.id === focus.id)
    if (!hangout) return

    map.flyTo([hangout.building.lat, hangout.building.lng], MAX_ZOOM - 1, {
      duration: 0.6,
    })
    /* Open after the flight so the popup lands in the right place. */
    const onEnd = () => {
      registry.get(focus.id)?.current?.openPopup()
      map.off('moveend', onEnd)
    }
    map.on('moveend', onEnd)
    return () => {
      map.off('moveend', onEnd)
    }
  }, [map, focus, hangouts, registry])

  return null
}

export default function CampusMapLive({
  position,
  hangouts = [],
  scheme = 'light',
  focus,
}) {
  const center = position ?? CAMPUS_CENTER
  const tiles = tileSource(scheme)
  /* id -> marker ref, so FocusHangout can open a popup by id.
     useMemo rather than useRef: a ref's .current may not be read during
     render, and this value is passed to children as a prop. */
  const registry = useMemo(() => new Map(), [])

  return (
    <MapContainer
      className="map-live"
      center={[center.lat, center.lng]}
      zoom={DEFAULT_ZOOM}
      maxZoom={MAX_ZOOM}
      maxBoundsViscosity={1.0}
      zoomControl={false}
      worldCopyJump={false}
      keyboard
      keyboardPanDelta={80}
      /* role=application tells a screen reader to pass arrow keys through
         to Leaflet's pan handler. The sheet's button list is the
         non-application way to reach the same data. */
      role="application"
      aria-label="Campus map. Use the arrow keys to pan, plus and minus to zoom."
    >
      {/* Keyed on scheme so a light/dark flip remounts the layer cleanly
          rather than relying on prop diffing inside Leaflet. */}
      <TileLayer
        key={tiles.url}
        url={tiles.url}
        attribution={tiles.attribution}
        maxZoom={tiles.maxZoom}
      />
      <ZoomControl position="topright" />
      <PanLimit center={center} radiusM={PAN_RADIUS_M} />
      <KeepSized />
      {position && <MeMarker position={position} />}
      {hangouts.map((h) => (
        <HangoutPin key={h.id} hangout={h} registry={registry} />
      ))}
      <FocusHangout focus={focus} hangouts={hangouts} registry={registry} />
    </MapContainer>
  )
}
