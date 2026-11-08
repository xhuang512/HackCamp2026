/* Every icon in the app, as inline stroke SVG so it takes `currentColor`.
   Decorative by default: pass a `label` only when the icon is the sole
   content of a control and nothing else names it. */

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
  badge: (
    <>
      <circle cx="12" cy="9" r="5.5" />
      <path d="m8.5 13.3-1 7 4.5-2.5 4.5 2.5-1-7" />
      <path d="m10.2 9 1.2 1.2L14 7.6" />
    </>
  ),
}

export default function Icon({ name, size = 22, label }) {
  const paths = PATHS[name]
  if (paths === undefined) return null

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
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
