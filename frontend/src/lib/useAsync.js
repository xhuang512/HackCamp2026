/* Run one api.js call and track its state. Keeps the loading, error and retry
   wiring out of every page.

   const { data, error, loading, reload } = useAsync(api.getMeNow)

   `fn` receives { signal } so a reload or unmount aborts the in-flight
   request instead of letting a stale response win.

   Loading is derived, not stored: the result carries the key of the request
   that produced it, and anything older than the current key reads as loading.
   That keeps setState out of the effect body and makes a stale response
   impossible to show. */

import { useCallback, useEffect, useState } from 'react'

export default function useAsync(fn, deps = []) {
  const [nonce, setNonce] = useState(0)
  const [result, setResult] = useState({ key: null, data: null, error: null })

  /* Cheap enough to recompute each render, and it keeps the effect's
     dependency list a single stable string. */
  const key = JSON.stringify([deps, nonce])

  const reload = useCallback(() => setNonce((n) => n + 1), [])

  useEffect(() => {
    const controller = new AbortController()
    let live = true

    fn({ signal: controller.signal })
      .then((data) => {
        if (live) setResult({ key, data, error: null })
      })
      .catch((error) => {
        if (!live || error?.name === 'AbortError') return
        setResult({ key, data: null, error })
      })

    return () => {
      live = false
      controller.abort()
    }
    /* `fn` is a module-level api.js function, stable across renders. */
    /* eslint-disable-next-line react-hooks/exhaustive-deps */
  }, [key])

  const loading = result.key !== key

  return {
    data: loading ? null : result.data,
    error: loading ? null : result.error,
    loading,
    reload,
  }
}
