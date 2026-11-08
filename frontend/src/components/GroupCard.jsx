import AvatarRow from './AvatarRow.jsx'
import SharedTags from './SharedTags.jsx'
import SpotRow from './SpotRow.jsx'

/* One group suggestion. The whole screen offers exactly one of these.
   `group` is the `group` object from GET /me/now. */

export default function GroupCard({ group, label, busy = false, onJoin, onSkip }) {
  const joined = group.my_state === 'joined' || group.my_state === 'checked_in'
  const invited = group.my_state === 'invited'

  return (
    <section className="card" aria-label="Your suggested group">
      <div className="card__top">
        <span className="card__label">{label}</span>
        <span className="card__meta">{group.joined_count} joined</span>
      </div>

      {joined && group.members.length > 0 && <AvatarRow members={group.members} />}
      <SharedTags shared={group.shared} />
      {group.spot ? (
        <SpotRow spot={group.spot} />
      ) : (
        <p className="waiting">
          Waiting for {group.needs} more {group.needs === 1 ? 'person' : 'people'} to confirm.
          The meeting building stays private until then.
        </p>
      )}

      {invited && (
        <div className="card__actions">
          <button type="button" className="btn btn--primary btn--lg" disabled={busy} onClick={onJoin}>
            {busy ? 'Joining…' : 'Join group'}
          </button>
          <button type="button" className="btn btn--ghost btn--lg" disabled={busy} onClick={onSkip}>
            Skip
          </button>
        </div>
      )}

      {joined && (
        <p className="group-status" role="status">
          {group.checked_in_count} of {group.joined_count} checked in
        </p>
      )}
    </section>
  )
}
