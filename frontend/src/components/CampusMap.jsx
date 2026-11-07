/* Placeholder campus map, straight from the mockup: three routes converging
   on one spot. AGENTS.md puts the real map on Leaflet via react-leaflet
   (not installed yet), so this is the dumb version with the same job:
   show where the group is meeting and roughly how far everyone is.
   Replacing it should not touch the Map page's layout. */

export default function CampusMap({ spotName = 'The Nest' }) {
  return (
    <div className="map-frame">
      <svg
        viewBox="0 0 350 330"
        preserveAspectRatio="xMidYMid slice"
        role="img"
        aria-label={`Map showing three walking routes converging on ${spotName}`}
      >
        <rect x="0" y="0" width="350" height="330" fill="var(--c-map-ground)" />
        <path d="M0 120 H350 M0 250 H350 M110 0 V330 M250 0 V330" stroke="var(--c-map-road)" strokeWidth="10" />

        <g fill="var(--c-map-building)">
          <rect x="20" y="20" width="70" height="80" rx="6" />
          <rect x="130" y="20" width="100" height="80" rx="6" />
          <rect x="270" y="140" width="64" height="92" rx="6" />
          <rect x="20" y="140" width="70" height="92" rx="6" />
          <rect x="130" y="270" width="100" height="44" rx="6" />
        </g>

        <rect x="135" y="145" width="90" height="82" rx="10" fill="var(--c-accent-soft)" stroke="var(--c-accent)" strokeWidth="2" />

        <g stroke="var(--c-accent)" strokeWidth="3" strokeDasharray="6 6" fill="none">
          <path d="M55 60 C 70 120, 120 150, 160 180" />
          <path d="M300 186 C 260 186, 240 186, 200 186" />
          <path d="M180 292 C 180 260, 180 240, 180 210" />
        </g>

        <g stroke="var(--c-bg)" strokeWidth="3">
          <circle cx="55" cy="60" r="11" fill="var(--c-av-2-bg)" />
          <circle cx="300" cy="186" r="11" fill="var(--c-av-3-bg)" />
          <circle cx="180" cy="292" r="11" fill="var(--c-ink)" />
        </g>
        <circle cx="180" cy="186" r="16" fill="var(--c-accent)" stroke="var(--c-bg)" strokeWidth="4" />

        <text x="180" y="166" textAnchor="middle" fontFamily="var(--font-sans)" fontSize="12" fontWeight="600" fill="var(--c-accent-dark)">
          {spotName}
        </text>
        <circle cx="300" cy="60" r="7" fill="var(--c-live)" stroke="var(--c-on-live)" strokeWidth="1.5" />
        <text x="300" y="44" textAnchor="middle" fontFamily="var(--font-sans)" fontSize="11" fontWeight="600" fill="var(--c-ink)">
          Koerner
        </text>
      </svg>
    </div>
  )
}
