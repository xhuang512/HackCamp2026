import SharedTags from './SharedTags.jsx'
import { formatGap } from '../lib/format.js'

/* Open groups, laid out as the 8138:2 frame draws them: the mode and the
   time on one line, then the place, then a bottom row with the action on
   the left and the seats on the right.

   Three things the frame shows that are not here, each for its own reason.
   It titles every card with a group description ("STAT 302 practice
   problems"), which no endpoint returns. It prints an exact building and
   floor on a card the reader has not joined, where AGENTS.md allows only
   the general area, so `area` fills that slot. And it puts the members'
   initials in the bottom-right; OpenGroupOut carries no joined count, and
   seats_left alone cannot be turned into one without knowing the group's
   capacity, so the seats go there instead of a row of invented circles. */

export default function OpenGroupList({ groups, busyId, onJoin }) {
  if (groups.length === 0) return null

  return (
    <section className="section" aria-labelledby="open-groups-title">
      <h2 className="section__title" id="open-groups-title">Open groups</h2>
      <ul className="rows">
        {groups.map((group) => (
          <li className="open-group" key={group.id}>
            <div className="open-group__head">
              <span className="open-group__mode">
                {group.mode === 'study' ? 'Study' : 'Social'}
              </span>
              <span className="open-group__when">{formatGap(group.gap)}</span>
            </div>

            <span className="open-group__name">{group.area}</span>

            {group.shared.length > 0 && <SharedTags shared={group.shared} />}

            <div className="open-group__foot">
              <button
                type="button"
                className="btn btn--primary"
                disabled={busyId !== null}
                onClick={() => onJoin(group.id)}
              >
                {busyId === group.id ? 'Joining…' : 'Join group'}
              </button>
              <span className="open-group__meta">
                {group.seats_left} {group.seats_left === 1 ? 'seat' : 'seats'} left
              </span>
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}
