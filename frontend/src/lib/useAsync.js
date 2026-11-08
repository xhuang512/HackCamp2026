/* Run one api.js call and track its state. Keeps the loading, error and retry
   wiring out of every page.

   const { data, error, loading, reload } = useAsync(api.getMeNow)
   const live = useAsync(api.getProjector, [], { pollMs: 5000 })

   `fn` receives { signal } so a reload or unmount aborts the in-flight
   request instead of letting a stale response win.

   Loading is derived, not stored: the result carries the key of the request
   that produced it, and anything older than the current key reads as loading.
   That keeps setState out of the effect body and makes a stale response
   impossible to show.

   `pollMs` refetches in the background. It deliberately does NOT go through
   `reload`, because bumping the key would make `loading` true on every tick
   and flash the loading state. A poll writes its result under the key that
   is already current, so the screen keeps its content and the numbers just
   change underneath. See the comment on `stale` for what a failed poll does. */

import { useCallback, useEffect, useRef, useState } from 'react'

export default function useAsync(fn, deps = [], { pollMs = 0 } = {}) {
  const [nonce, setNonce] = useState(0)
  const [result, setResult] = useState({
    key: null,
    data: null,
    error: null,
    stale: false,
  })

  /* Cheap enough to recompute each render, and it keeps the effect's
     dependency list a single stable string. */
  const key = JSON.stringify([deps, nonce])

  const reload = useCallback(() => setNonce((n) => n + 1), [])

  useEffect(() => {
    const controller = new AbortController()
    let live = true

    fn({ signal: controller.signal })
      .then((data) => {
        if (live) setResult({ key, data, error: null, stale: false })
      })
      .catch((error) => {
        if (!live || error?.name === 'AbortError') return
        setResult({ key, data: null, error, stale: false })
      })

    return () => {
      live = false
      controller.abort()
    }
    /* `fn` is a module-level api.js function, stable across renders. */
    /* eslint-disable-next-line react-hooks/exhaustive-deps */
  }, [key])

  /* One in-flight poll at a time, aborted on unmount. Without the ref a slow
     response and a short interval would stack requests on a backend that is
     already struggling, which is exactly when polling should back off. */
  const polling = useRef(null)

  useEffect(() => {
    if (!pollMs) return undefined

    function tick() {
      /* A hidden tab is a phone in a pocket. Nothing is read, so nothing is
         worth fetching or spending battery on. */
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return
      if (polling.current !== null) return

      const controller = new AbortController()
      polling.current = controller

      fn({ signal: controller.signal })
        .then((data) => {
          setResult((prev) => (prev.key === key ? { key, data, error: null, stale: false } : prev))
        })
        .catch((error) => {
          if (error?.name === 'AbortError') return
          /* A failed background poll keeps the last good data rather than
             replacing the screen with an error. On the projector that is the
             difference between a stale number and a blank stage mid-demo.
             `stale` is how the screen says so without hiding anything. The
             first load still fails loudly, through `error` above. */
          setResult((prev) => (prev.key === key ? { ...prev, stale: true } : prev))
        })
        .finally(() => {
          if (polling.current === controller) polling.current = null
        })
    }

    let timeoutId
    const schedule = () => {
      timeoutId = setTimeout(() => {
        tick()
        schedule()
      }, pollMs)
    }
    schedule()

    /* Coming back to a tab should not wait out the rest of an interval. */
    const onVisible = () => {
      if (document.visibilityState === 'visible') tick()
    }
    document.addEventListener('visibilitychange', onVisible)

    return () => {
      clearTimeout(timeoutId)
      document.removeEventListener('visibilitychange', onVisible)
      if (polling.current !== null) {
        polling.current.abort()
        polling.current = null
      }
    }
    /* eslint-disable-next-line react-hooks/exhaustive-deps */
  }, [key, pollMs])

  const loading = result.key !== key

  return {
    data: loading ? null : result.data,
    error: loading ? null : result.error,
    loading,
    /* True when the last background poll failed but earlier data is still on
       screen. Always false while loading or erroring. */
    stale: !loading && result.error === null && result.stale,
    reload,
  }
}
