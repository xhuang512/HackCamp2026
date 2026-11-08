/* Every icon in the app, as inline stroke SVG so it takes `currentColor`.
   Decorative by default: pass a `label` only when the icon is the sole
   content of a control and nothing else names it. */

/* Solid silhouettes of the three navigation icons. The tab bar uses these
   to mark the active tab by SHAPE rather than by colour alone, which is
   what keeps an icon-only bar readable without the labels. */
const FILLED = {
  group: (
    <>
      <circle cx="9.2" cy="8.4" r="3.6" />
      <path d="M2.6 19.8c1.1-3.5 3.6-5.2 6.6-5.2s5.5 1.7 6.6 5.2z" />
      <path d="M16.1 5.4a3.2 3.2 0 0 1 0 7.4 4.4 4.4 0 0 0 0-7.4z" />
      <path d="M17.6 14.6c1.9.6 3.2 2 3.8 3.8h-3.2a9.3 9.3 0 0 0-1.9-3.6z" />
    </>
  ),
  map: (
    <>
      <path d="M8.6 3.6 3 5.7v14.7l5.6-2.1z" />
      <path d="M9.9 3.6v14.7l4.2 1.4V5z" />
      <path d="M15.4 5v14.7L21 17.6V2.9z" />
    </>
  ),
  person: (
    <>
      <circle cx="12" cy="8.2" r="4" />
      <path d="M4.4 20.4c1.3-3.8 4.2-5.6 7.6-5.6s6.3 1.8 7.6 5.6z" />
    </>
  ),
}

const PATHS = {
  clock: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </>
  ),
  map: (
    <>
      <path d="M9 4 3.5 6v14L9 18l6 2 5.5-2V4L15 6 9 4z" />
      <path d="M9 4v14M15 6v14" />
    </>
  ),
  person: (
    <>
      <circle cx="12" cy="8.5" r="3.5" />
      <path d="M5 20c1.2-3.5 4-5 7-5s5.8 1.5 7 5" />
    </>
  ),
  group: (
    <>
      <circle cx="9.2" cy="8.6" r="3.2" />
      <path d="M3.2 19.4c1-3.1 3.3-4.6 6-4.6s5 1.5 6 4.6" />
      <path d="M16.4 6.1a3.2 3.2 0 0 1 0 6M18.2 14.9c1.6.7 2.6 1.9 3.1 3.4" />
    </>
  ),
  pin: (
    <>
      <path d="M12 21s-6-5.3-6-10a6 6 0 0 1 12 0c0 4.7-6 10-6 10z" />
      <circle cx="12" cy="11" r="2.2" />
    </>
  ),
  scan: (
    <>
      <path d="M8 8a6 6 0 0 1 8 0M5 5a10 10 0 0 1 14 0" />
      <rect x="8" y="11" width="8" height="10" rx="2" />
    </>
  ),
  lock: (
    <>
      <rect x="5" y="10.5" width="14" height="9.5" rx="2" />
      <path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5" />
    </>
  ),
  /* From origin/feat/badges. */
  badge: (
    <>
      <circle cx="12" cy="9" r="5.5" />
      <path d="m8.5 13.3-1 7 4.5-2.5 4.5 2.5-1-7" />
      <path d="m10.2 9 1.2 1.2L14 7.6" />
    </>
  ),
}

export default function Icon({ name, size = 22, label, filled = false }) {
  /* A filled variant is only drawn where one exists. Asking for one that
     does not falls back to the stroke icon rather than rendering nothing. */
  const solid = filled ? FILLED[name] : undefined
  const paths = solid ?? PATHS[name]
  if (paths === undefined) return null

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={solid === undefined ? 'none' : 'currentColor'}
      stroke={solid === undefined ? 'currentColor' : 'none'}
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...(label === undefined
        ? { 'aria-hidden': 'true' }
        : { role: 'img', 'aria-label': label })}
    >
      {paths}
    </svg>
  )
}
