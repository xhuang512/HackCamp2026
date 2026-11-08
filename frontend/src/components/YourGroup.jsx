import { Link } from 'react-router-dom'
import AvatarRow from './AvatarRow.jsx'
import SharedTags from './SharedTags.jsx'
import { formatDay, formatRange } from '../lib/format.js'

/* "Your group", the redesign's joined state: a back link, the group card
   with a grey place panel, and one big check-in button.

   Left out because nothing backs them: "Alex is your captain" (there is no
   host role, and the Group Creator has no special check-in role) and
   "Leave group" (no endpoint). */

export default function YourGroup({ group, gap, onBack, onCheckIn }) {
  const modeName = group.mode === 'study' ? 'Study' : group.mode === 'social' ? 'Social' : group.mode
  const checkInOpen = group.state === 'confirmed' || group.state === 'active'

  return (
    <>
      <button type="button" className="rd-back" onClick={onBack}>‹ Groups</button>
      <header className="rd-head rd-head--tight">
        <h1 className="rd-title">Your group</h1>
      </header>

      <section className="rd-card" aria-label="Your group">
        <h2 className="rd-card__title">{modeName} group</h2>
        <p className="rd-card__meta">
          <span aria-hidden="true">✓ </span>Joined
          {gap ? ` · ${formatDay(gap.day)}, ${formatRange(gap)}` : ''}
        </p>
        <AvatarRow members={group.members} />
        <SharedTags shared={group.shared} />

        {group.spot ? (
          <div className="rd-panel rd-panel--grey">
            <strong className="rd-panel__title">{group.spot.building}</strong>
            <span className="rd-panel__text">
              {group.spot.walk_min} min walk · {group.joined_count} joined
            </span>
            <Link to="/map" className="rd-link">View on map ›</Link>
          </div>
        ) : (
          <p className="waiting">
            Waiting for {group.needs} more {group.needs === 1 ? 'person' : 'people'} to confirm.
            The meeting building stays private until then.
          </p>
        )}

        {checkInOpen && (
          <button type="button" className="btn btn--primary btn--lg btn--block" onClick={onCheckIn}>
            Scan to check in
          </button>
        )}
      </section>

      <p className="rd-status" role="status">
        {group.checked_in_count} of {group.joined_count} checked in
      </p>
    </>
  )
}
