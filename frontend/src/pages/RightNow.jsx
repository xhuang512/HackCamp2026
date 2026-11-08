import { useEffect, useState } from 'react'
import * as api from '../lib/api.js'
import useAsync from '../lib/useAsync.js'
import { formatDay, formatRange, vancouverNow } from '../lib/format.js'
import ModeToggle from '../components/ModeToggle.jsx'
import GroupCard from '../components/GroupCard.jsx'
import StateCard from '../components/StateCard.jsx'
import OpenGroupList from '../components/OpenGroupList.jsx'
import StartGroupForm from '../components/StartGroupForm.jsx'
import YourGroup from '../components/YourGroup.jsx'
import CheckInScreen from '../components/CheckInScreen.jsx'

/* The Groups tab, from the redesign frames: Groups, Your group, and the
   check-in screen behind its button. The data and every call are the ones
   this screen already made; only the layout is new.

   The mode toggle picks the mode for a group the student starts. It does
   not filter the suggestion: GET /me/now takes no mode parameter, so the
   matcher's group arrives with a mode of its own, and anything describing
   that group reads group.mode, never this toggle. */

function Clock() {
  const [now, setNow] = useState(() => vancouverNow())
  useEffect(() => {
    const id = window.setInterval(() => setNow(vancouverNow()), 15000)
    return () => window.clearInterval(id)
  }, [])
  return <time className="rd-head__aside">{now}</time>
}

export default function RightNow() {
  const [mode, setMode] = useState('social')
  const [busyId, setBusyId] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [start, setStart] = useState(null)
  const [starting, setStarting] = useState(false)
  /* null means "follow the data": a joined group opens on Your group. */
  const [screen, setScreen] = useState(null)
  const { data, error, loading, reload } = useAsync(api.getMeNow)
  const open = useAsync(api.getOpenGroups)
  const catalog = useAsync(api.getOptions)

  async function respond(action, groupId) {
    setBusyId(groupId)
    setActionError(null)
    try {
      await action(groupId)
      setScreen(null)
      reload()
      open.reload()
    } catch (err) {
      setActionError(err)
    } finally {
      setBusyId(null)
    }
  }

  async function create(building) {
    setStarting(true)
    setActionError(null)
    try {
      await api.createGroup({ building, mode, now: start === 'now' })
      setStart(null)
      setScreen(null)
      reload()
    } catch (err) {
      setActionError(err)
    } finally {
      setStarting(false)
    }
  }

  const group = data?.group ?? null
  const gap = data?.gap ?? null
  const joined = group !== null && ['joined', 'checked_in'].includes(group.my_state)
  const current = screen ?? (joined ? 'group' : 'groups')

  if (joined && current === 'group') {
    return (
      <YourGroup
        group={group}
        gap={gap}
        onBack={() => setScreen('groups')}
        onCheckIn={() => setScreen('checkin')}
      />
    )
  }

  if (joined && current === 'checkin') {
    return (
      <CheckInScreen
        group={group}
        gap={gap}
        onBack={() => setScreen('group')}
        onCheckedIn={reload}
      />
    )
  }

  return (
    <>
      <header className="rd-head">
        <h1 className="rd-title">Groups</h1>
        <Clock />
      </header>

      <section className="rd-block" aria-labelledby="availability-title">
        <h2 className="rd-h2" id="availability-title">My availability</h2>
        <p className="rd-sub">
          {gap ? `${formatDay(gap.day)} · ${formatRange(gap)}` : 'No free time found yet'}
        </p>
      </section>

      <ModeToggle value={mode} onChange={setMode} />

      {loading && <StateCard title="Finding your group" />}

      {error && (
        <StateCard title="Could not load your group" onRetry={reload}>
          {error.status === 0
            ? 'The backend is not reachable. Start it with uvicorn app.main:app --reload, or turn fixture mode on.'
            : error.message}
        </StateCard>
      )}

      {actionError && !start && <StateCard title="That did not work">{actionError.message}</StateCard>}

      {start && (
        <StartGroupForm
          now={start === 'now'}
          mode={mode}
          buildings={catalog.data?.buildings ?? []}
          loadingBuildings={catalog.loading}
          buildingError={catalog.error}
          onRetryBuildings={catalog.reload}
          busy={starting}
          error={starting ? null : actionError}
          onSubmit={create}
          onCancel={() => setStart(null)}
        />
      )}

      {group && !joined && (
        <GroupCard
          group={group}
          gap={gap}
          busy={busyId === group.id}
          onJoin={() => respond(api.joinGroup, group.id)}
          onSkip={() => respond(api.skipGroup, group.id)}
        />
      )}

      {/* Joined, but the student came back to the list. */}
      {joined && (
        <button type="button" className="rd-panel rd-panel--button" onClick={() => setScreen('group')}>
          <span className="rd-panel__title">You joined a group</span>
          <span className="rd-panel__text">{group.checked_in_count} of {group.joined_count} checked in</span>
          <span className="rd-link">View your group ›</span>
        </button>
      )}

      {data && group === null && !start && (
        <>
          {open.loading && <StateCard title="Looking for open groups" />}
          {open.error && <StateCard title="Could not load open groups" onRetry={open.reload}>{open.error.message}</StateCard>}
          {open.data?.length === 0 && (
            <StateCard title="No open groups yet">
              Start one for this gap and the matcher will fill it as students join.
            </StateCard>
          )}
          {open.data && <OpenGroupList groups={open.data} busyId={busyId} onJoin={(id) => respond(api.joinGroup, id)} />}
        </>
      )}

      {!start && (
        <div className="rd-actions rd-actions--page">
          {data && group === null && (
            <button type="button" className="btn btn--primary btn--lg" onClick={() => setStart('gap')}>Start a group</button>
          )}
          <button type="button" className="btn btn--ghost btn--lg" onClick={() => setStart('now')}>
            I&apos;m free now
          </button>
        </div>
      )}
    </>
  )
}
