import AvatarRow from './AvatarRow.jsx'
import SharedTags from './SharedTags.jsx'
import SpotRow from './SpotRow.jsx'

/* One group suggestion. The whole screen offers exactly one of these.
   `group` is the `group` object from GET /me/now. */

export default function GroupCard({ group, label, busy = false, onJoin, onSkip }) {
  const joined = group.response === 'joined'
  const people = group.members.length + 1

  return (
    <section className="card" aria-label="Your suggested group">
      <div className="card__top">
        <span className="card__label">{label}</span>
        <span className="card__meta">{people} people</span>
      </div>

      <AvatarRow members={group.members} />
      <SharedTags shared={group.shared} />
      <SpotRow spot={group.spot} />

      <div className="card__actions">
        <button
          type="button"
          className="btn btn--primary btn--lg"
          disabled={busy || joined}
          onClick={onJoin}
        >
          {joined ? "You're in" : 'Join group'}
        </button>
        <button
          type="button"
          className="btn btn--ghost btn--lg"
          disabled={busy || joined}
          onClick={onSkip}
        >
          Skip
        </button>
      </div>
    </section>
  )
}
