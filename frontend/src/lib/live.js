/* Supabase realtime, in its walking-skeleton form.

   The signature is final: useLive(channel, { initial }) returns the latest
   payload and a connection status. The projector counter uses it first, then
   group chat and the clustering view reuse the same call.

   The body is deliberately dumb. @supabase/supabase-js is not installed and
   no anon key is set, so the hook holds `initial` and never claims to be
   connected. Swapping in the real client means replacing the body of this
   file, never the signature, so no component changes.

   When wiring it up:
     npm i @supabase/supabase-js
     VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY in .env.local
   The anon key only reads realtime channels. Every write goes through the
   backend, with row level security on every table. */

import { useEffect } from 'react'

const URL = import.meta.env.VITE_SUPABASE_URL
const ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY

/* ---------- The polling fallback ----------

   Until the realtime client above is wired up, screens that have to change
   on their own refetch on a timer through useAsync's `pollMs`. The cadences
   live here, next to the hook that will replace them, so switching to
   realtime is one file rather than a hunt through the pages.

   The projector is the fast one because a demo depends on it: AGENTS.md's
   demo check has two phones checking each other in and the stage count going
   up, and nobody wants to count to fifteen on stage. The map is slower
   because building activity changes slowly and the map runs on a phone,
   where every wakeup costs battery. */

/** Stage screen on a laptop. Fast, mains powered, watched by a room. */
export const PROJECTOR_POLL_MS = 5000

/** Map on a student's phone. Slow enough to be cheap. */
export const MAP_POLL_MS = 15000

/** Both credentials present. False means the hook is offline by design. */
export const liveReady = Boolean(URL && ANON_KEY)

/**
 * Subscribe to one realtime channel.
 * @param {string} channel e.g. 'projector_state'
 * @param {{ initial?: unknown }} options
 * @returns {{ data: unknown, status: 'offline' | 'connecting' | 'live' | 'error' }}
 */
export function useLive(channel, { initial = null } = {}) {
  useEffect(() => {
    if (!liveReady) return
    console.warn(
      `useLive("${channel}"): Supabase credentials are set but the client is not wired up yet. See src/lib/live.js.`,
    )
  }, [channel])

  /* The real version holds { data, status } in state and updates it from the
     channel callbacks:

       const [live, setLive] = useState({ data: initial, status: 'connecting' })
       useEffect(() => {
         const client = createClient(URL, ANON_KEY)
         const sub = client
           .channel(channel)
           .on('broadcast', { event: '*' }, ({ payload }) =>
             setLive({ data: payload, status: 'live' }))
           .subscribe()
         return () => { client.removeChannel(sub) }
       }, [channel])
       return live

     Until then, report the truth rather than a hopeful 'connecting'. */
  return { data: initial, status: liveReady ? 'error' : 'offline' }
}
