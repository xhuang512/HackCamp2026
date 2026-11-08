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
import { placeLabel } from '../lib/hangouts.js'

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

/* One pin per building.

   Leaflet divIcons are plain divs, so the accessible name and role are set
   through the marker element in an effect: Leaflet's own `alt` option only
   applies to image icons. The label carries a place and a count, and never
   a name.

   The student's own meeting building gets its own glyph and modifier class
   rather than only a different colour, because mode and ownership must not
   be carried by hue alone. */
function PlacePin({ place, registry }) {
  const markerRef = useRef(null)
  const label = placeLabel(place)

  const icon = useMemo(
    () =>
      L.divIcon({
        className: '',
        html:
          `<span class="pin pin--${place.mine ? 'mine' : 'social'}">` +
          (place.mine
            ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 21s-6.5-5.3-6.5-10a6.5 6.5 0 1 1 13 0c0 4.7-6.5 10-6.5 10z"/><circle cx="12" cy="11" r="2.4"/></svg>'
            : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="9" cy="8.5" r="2.8"/><path d="M3.5 19c.9-2.8 3-4.2 5.5-4.2s4.6 1.4 5.5 4.2"/><path d="M16 6.2a2.8 2.8 0 0 1 0 5.3M18 14.4c1.6.6 2.7 1.8 3.3 3.4"/></svg>') +
          `<span class="pin__count">${place.groupsMeeting || place.count}</span>` +
          '</span>',
        iconSize: [44, 44],
        /* Anchor at the bottom centre so the pin points at the building. */
        iconAnchor: [22, 44],
        popupAnchor: [0, -44],
      }),
    [place.mine, place.count, place.groupsMeeting],
  )

  useEffect(() => {
    const el = markerRef.current?.getElement()
    if (!el) return
    /* Leaflet's own `alt` option only applies to image icons, so the role
       and name go on the element directly. */
    el.setAttribute('role', 'button')
    el.setAttribute('aria-label', label)
  }, [label])

  /* Let FocusPlace open this marker's popup by id. */
  useEffect(() => {
    if (!registry) return undefined
    registry.set(place.id, markerRef)
    return () => {
      registry.delete(place.id)
    }
  }, [registry, place.id])

  return (
    <Marker
      ref={markerRef}
      position={[place.lat, place.lng]}
      icon={icon}
      keyboard
    >
      <Popup>
        <strong>{place.name}</strong>
        <br />
        {label}
      </Popup>
    </Marker>
  )
}

/* Flies to one building and opens its popup when `focus` changes.

   Driven by a plain prop so MapPage never holds a Leaflet ref: everything
   Leaflet-shaped stays inside this lazily loaded module. `focus.nonce`
   makes a repeat tap on the same row fly again. */
function FocusPlace({ focus, places, registry }) {
  const map = useMap()

  useEffect(() => {
    if (!focus?.id) return
    const place = places.find((item) => item.id === focus.id)
    if (!place) return

    map.flyTo([place.lat, place.lng], MAX_ZOOM - 1, {
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
  }, [map, focus, places, registry])

  return null
}

export default function CampusMapLive({
  position,
  places = [],
  scheme = 'light',
  focus,
}) {
  const center = position ?? CAMPUS_CENTER
  const tiles = tileSource(scheme)
  /* id -> marker ref, so FocusPlace can open a popup by id.
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
      {places.map((place) => (
        <PlacePin key={place.id} place={place} registry={registry} />
      ))}
      <FocusPlace focus={focus} places={places} registry={registry} />
    </MapContainer>
  )
}
