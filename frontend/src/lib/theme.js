/* Which colour scheme the app is in, and where that choice is kept.

   The app used to follow the phone through prefers-color-scheme alone, with
   no way to disagree with it. Two things made that a problem: the Figma file
   is drawn in light only, so a judge on a dark phone never saw the design as
   designed, and a demo running on four phones looked like four apps.

   So the choice is the app's, and light is the default. tokens.css carries
   both palettes and switches on data-theme on <html>, which index.html sets
   before first paint. Nothing here reads prefers-color-scheme; a student who
   wants dark asks for it on the Me tab and the phone is not consulted. */

export const THEME_KEY = 'hangout.theme'
export const DEFAULT_THEME = 'light'

/* The <html> colours a viewer sees before any CSS has painted, and the
   browser UI around the page on a phone. Kept beside the tokens they come
   from: --bg in light, and dark mode's --bg. */
const THEME_COLOR = { light: '#ffffff', dark: '#00162e' }

const listeners = new Set()

function valid(theme) {
  return theme === 'light' || theme === 'dark'
}

/** The saved choice, or light. Safe with no DOM and no storage. */
export function readTheme() {
  try {
    const saved = localStorage.getItem(THEME_KEY)
    return valid(saved) ? saved : DEFAULT_THEME
  } catch {
    /* Private browsing can throw on access. */
    return DEFAULT_THEME
  }
}

/** Put `theme` on <html>, where tokens.css and the browser UI read it. */
export function applyTheme(theme) {
  if (typeof document === 'undefined') return
  const next = valid(theme) ? theme : DEFAULT_THEME
  document.documentElement.setAttribute('data-theme', next)
  /* Without this the browser keeps styling its own widgets to the phone's
     setting, so a dark phone renders black dropdowns and black time pickers
     on a light page. The schedule editor is two time inputs per row, which
     is where that shows up worst. */
  document.documentElement.style.colorScheme = next
  const meta = document.querySelector('meta[name="theme-color"]')
  if (meta !== null) meta.setAttribute('content', THEME_COLOR[next])
}

/** Save `theme`, apply it, and tell everything reading it. */
export function setTheme(theme) {
  const next = valid(theme) ? theme : DEFAULT_THEME
  try {
    localStorage.setItem(THEME_KEY, next)
  } catch {
    /* The choice still applies to this page, it just will not survive. */
  }
  applyTheme(next)
  for (const listener of listeners) listener()
}

/** For useSyncExternalStore. Returns the unsubscribe function. */
export function subscribeTheme(onChange) {
  listeners.add(onChange)
  return () => listeners.delete(onChange)
}
