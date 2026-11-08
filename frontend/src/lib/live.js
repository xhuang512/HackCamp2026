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
