import AvatarRow from './AvatarRow.jsx'
import SharedTags from './SharedTags.jsx'
import { formatRange } from '../lib/format.js'

/* The suggested group on the Groups screen, as the redesign draws it: title
   and time on one line, who is in it, what it shares, the place, then one
   Join button. `group` is the `group` object from GET /me/now.

   The frame also shows a group description and "Meet again next week".
   Neither exists in the API, so neither is drawn. */

export default function GroupCard({ group, gap, busy = false, onJoin, onSkip }) {
  const invited = group.my_state === 'invited'
  const modeName = group.mode === 'study' ? 'Study' : group.mode === 'social' ? 'Social' : group.mode

  return (
    <section className="rd-card" aria-label="Your suggested group">
      <div className="rd-card__head">
        <h2 className="rd-card__title">{modeName} group</h2>
        {gap && <span className="rd-card__time">{formatRange(gap)}</span>}
      </div>

      <p className="rd-card__meta">
        {group.joined_count} joined · {group.seats_left} {group.seats_left === 1 ? 'seat' : 'seats'} left
      </p>

      {group.members.length > 0 && <AvatarRow members={group.members} />}
      <SharedTags shared={group.shared} />

      {/* The backend sends no spot for two different reasons, and they need
          different sentences: not enough people have confirmed yet, or the
          group has confirmed and this reader has not joined it. */}
      {group.spot ? (
        <p className="rd-card__place">{group.spot.building}</p>
      ) : group.needs > 0 ? (
        <p className="waiting">
          Waiting for {group.needs} more {group.needs === 1 ? 'person' : 'people'} to confirm.
          The meeting building stays private until then.
        </p>
      ) : (
        <p className="waiting">
          This group is confirmed. Join it to see where everyone is meeting.
        </p>
      )}

      {invited && (
        <div className="rd-actions">
          <button type="button" className="btn btn--primary btn--lg" disabled={busy} onClick={onJoin}>
            {busy ? 'Joining…' : 'Join group'}
          </button>
          <button type="button" className="btn btn--ghost btn--lg" disabled={busy} onClick={onSkip}>
            Skip
          </button>
        </div>
      )}
    </section>
  )
}
