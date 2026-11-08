/* The app's colour scheme, in JavaScript.

   CSS reads it off data-theme on <html>, but a Leaflet tile URL is built in
   JS and a selector cannot reach it. This hook is that bridge, and nothing
   else should need it.

   It deliberately does NOT read prefers-color-scheme. The scheme is the
   app's own choice now (src/lib/theme.js), so the map's tiles follow the
   toggle on the Me tab rather than the phone, and a light app never ends up
   with a dark basemap in the middle of it. */

import { useSyncExternalStore } from 'react'
import { DEFAULT_THEME, readTheme, subscribeTheme } from './theme.js'

/** @returns {'light' | 'dark'} */
export default function useColorScheme() {
  /* Server snapshot is the default. There is no SSR in production; this only
     keeps a renderToString smoke check from throwing. */
  return useSyncExternalStore(subscribeTheme, readTheme, () => DEFAULT_THEME)
}
