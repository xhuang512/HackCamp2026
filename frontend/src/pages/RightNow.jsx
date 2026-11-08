import { useState } from 'react'
import * as api from '../lib/api.js'
import useAsync from '../lib/useAsync.js'
import { formatGap, formatDay } from '../lib/format.js'
import ScreenHeader from '../components/ScreenHeader.jsx'
import ModeToggle from '../components/ModeToggle.jsx'
import GroupCard from '../components/GroupCard.jsx'
import StateCard from '../components/StateCard.jsx'
import OpenGroupList from '../components/OpenGroupList.jsx'
import StartGroupForm from '../components/StartGroupForm.jsx'
import CheckInCode from '../components/CheckInCode.jsx'
import CheckInScanner from '../components/CheckInScanner.jsx'

/* The screen the whole app is for: one gap, one group, join or skip.

   The mode toggle picks the mode for a group the student starts. It does
   not filter the suggestion: GET /me/now takes no mode parameter, so the
   matcher's group arrives with a mode of its own. Anything describing that
   group therefore reads group.mode, never this toggle. Making GET /me/now
   take a mode is a contract change worth raising first. */

export default function RightNow() {
  const [mode, setMode] = useState('social')
  const [busyId, setBusyId] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [start, setStart] = useState(null)
  const [starting, setStarting] = useState(false)
  const { data, error, loading, reload } = useAsync(api.getMeNow)
  const open = useAsync(api.getOpenGroups)
  const catalog = useAsync(api.getOptions)

  async function respond(action, groupId) {
    setBusyId(groupId)
    setActionError(null)
    try {
      await action(groupId)
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
      reload()
    } catch (err) {
      setActionError(err)
    } finally {
      setStarting(false)
    }
  }

  /* The suggested group's own mode, which is not necessarily the toggle's.
     ModeBadge on the card spells the mode out, so the heading does not
     repeat it. */
  const label = data?.group?.my_state === 'invited' ? 'Suggested for this gap' : 'Your group for this gap'

  return (
    <>
      <ScreenHeader
        eyebrow={data?.gap ? `Your next gap, ${formatDay(data.gap.day)}` : 'Your next gap'}
        title={data?.gap ? formatGap(data.gap) : '—'}
        action={
          <button type="button" className="btn btn--outline" onClick={() => setStart('now')}>
            I&apos;m free now
          </button>
        }
      />

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

      {data && data.group && (
        <GroupCard
          group={data.group}
          label={label}
          busy={busyId === data.group.id}
          onJoin={() => respond(api.joinGroup, data.group.id)}
          onSkip={() => respond(api.skipGroup, data.group.id)}
        />
      )}

      {data?.group && ['joined', 'checked_in'].includes(data.group.my_state) && (
        <div className="checkin-grid">
          <CheckInCode groupId={data.group.id} />
          <CheckInScanner groupId={data.group.id} onCheckedIn={reload} />
        </div>
      )}

      {data && data.group === null && !start && (
        <>
          {open.loading && <StateCard title="Looking for open groups" />}
          {open.error && <StateCard title="Could not load open groups" onRetry={open.reload}>{open.error.message}</StateCard>}
          {open.data?.length === 0 && (
            <StateCard title="No open groups yet">
              Start one for this gap and the matcher will fill it as students join.
            </StateCard>
          )}
          {open.data && <OpenGroupList groups={open.data} busyId={busyId} onJoin={(id) => respond(api.joinGroup, id)} />}
          <div className="page-action">
            <button type="button" className="btn btn--primary btn--lg" onClick={() => setStart('gap')}>Start a group</button>
          </div>
        </>
      )}
    </>
  )
}
