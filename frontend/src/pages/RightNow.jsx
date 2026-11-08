import { useState } from 'react'
import * as api from '../lib/api.js'
import useAsync from '../lib/useAsync.js'
import { formatGap, formatDay } from '../lib/format.js'
import ScreenHeader from '../components/ScreenHeader.jsx'
import ModeToggle from '../components/ModeToggle.jsx'
import GroupCard from '../components/GroupCard.jsx'
import StateCard from '../components/StateCard.jsx'

/* The screen the whole app is for: one gap, one group, join or skip.
   Mode is local for now. Once the backend takes it, it becomes a parameter
   on GET /me/now, which is a contract change worth raising first. */

export default function RightNow() {
  const [mode, setMode] = useState('social')
  const [busy, setBusy] = useState(false)
  const { data, error, loading, reload } = useAsync(api.getMeNow)

  async function respond(action, groupId) {
    setBusy(true)
    try {
      await action(groupId)
      reload()
    } catch (err) {
      console.error(err)
      setBusy(false)
    }
  }

  const label = mode === 'social' ? 'Your group for this gap' : 'Your quiet study group'

  return (
    <>
      <ScreenHeader
        eyebrow={data ? `Your next gap, ${formatDay(data.gap.day)}` : 'Your next gap'}
        title={data ? formatGap(data.gap) : '—'}
        action={
          <button type="button" className="btn btn--outline">
            I&apos;m free now
          </button>
        }
      />

      <ModeToggle value={mode} onChange={setMode} />

      {loading && <StateCard title="Finding your group" />}

      {error && (
        <StateCard title="Could not load your group" onRetry={reload}>
          {error.status === 0
            ? 'The backend is not reachable. Start it with uvicorn app.main:app --reload, or leave VITE_USE_FIXTURES on.'
            : error.message}
        </StateCard>
      )}

      {data && data.group === null && (
        <StateCard title="No group yet">
          Nobody else is free in this gap so far. We will suggest one as more
          students add their schedules.
        </StateCard>
      )}

      {data && data.group && (
        <GroupCard
          group={data.group}
          label={label}
          busy={busy}
          onJoin={() => respond(api.joinGroup, data.group.id)}
          onSkip={() => respond(api.skipGroup, data.group.id)}
        />
      )}

      <p className="note">
        Met Tuesday&apos;s group before? We&apos;ll suggest them again next week.
      </p>
    </>
  )
}
