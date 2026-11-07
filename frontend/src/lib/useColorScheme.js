/* The viewer's colour scheme, in JavaScript.

   CSS already handles this through prefers-color-scheme, but a tile URL is
   built in JS and a media query cannot reach it. This hook is that bridge,
   and nothing else should need it. */

import { useCallback, useSyncExternalStore } from 'react'

const QUERY = '(prefers-color-scheme: dark)'

function subscribe(onChange) {
  if (typeof window === 'undefined' || !window.matchMedia) return () => {}
  const mq = window.matchMedia(QUERY)
  mq.addEventListener('change', onChange)
  return () => mq.removeEventListener('change', onChange)
}

/** @returns {'light' | 'dark'} */
export default function useColorScheme() {
  const snapshot = useCallback(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return 'light'
    return window.matchMedia(QUERY).matches ? 'dark' : 'light'
  }, [])

  /* Server snapshot is 'light'. There is no SSR in production; this only
     keeps a renderToString smoke check from throwing. */
  return useSyncExternalStore(subscribe, snapshot, () => 'light')
}
