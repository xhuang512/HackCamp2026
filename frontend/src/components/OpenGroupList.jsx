import SharedTags from './SharedTags.jsx'
import { formatGap } from '../lib/format.js'

export default function OpenGroupList({ groups, busyId, onJoin }) {
  if (groups.length === 0) return null

  return (
    <section className="section" aria-labelledby="open-groups-title">
      <h2 className="section__title" id="open-groups-title">Open groups</h2>
      <ul className="rows">
        {groups.map((group) => (
          <li className="open-group" key={group.id}>
            <div className="row__text">
              <span className="row__name">{group.area}</span>
              <span className="row__meta">
                {formatGap(group.gap)} · {group.seats_left} {group.seats_left === 1 ? 'seat' : 'seats'} left
              </span>
            </div>
            {group.shared.length > 0 && <SharedTags shared={group.shared} />}
            <button
              type="button"
              className="btn btn--primary"
              disabled={busyId !== null}
              onClick={() => onJoin(group.id)}
            >
              {busyId === group.id ? 'Joining…' : 'Join'}
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
