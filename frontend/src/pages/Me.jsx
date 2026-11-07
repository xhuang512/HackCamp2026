import * as api from '../lib/api.js'
import useAsync from '../lib/useAsync.js'
import ScreenHeader from '../components/ScreenHeader.jsx'
import StateCard from '../components/StateCard.jsx'
import Icon from '../components/Icon.jsx'

/* The mockup has no Me screen (its "Me" tab points at the onboarding
   artboard), so this is built from the privacy rules in AGENTS.md rather
   than from a drawing. Treat the layout as a placeholder and the rules as
   the part that matters:
     - the hangout count and the timetable are private to their owner
     - tags are the only thing other students see, beside the free block
     - pause and visibility are always respected by matching */

const TAG_LABELS = {
  international: 'International',
  transfer: 'Transfer',
  exchange: 'Exchange',
  commuter: 'Commuter',
}

export default function Me() {
  const { data, error, loading, reload } = useAsync(api.getMe)

  return (
    <>
      <ScreenHeader eyebrow="Your account" title="Me" small />

      {loading && <StateCard title="Loading your profile" />}

      {error && (
        <StateCard title="Could not load your profile" onRetry={reload}>
          {error.message}
        </StateCard>
      )}

      {data && (
        <>
          <div className="me-id">
            <span className="me-id__avatar" aria-hidden="true">
              {data.first_name[0].toUpperCase()}
            </span>
            <div className="screen-head__text">
              <span className="screen-head__title screen-head__title--sm">
                {data.first_name}
              </span>
              <span className="screen-head__eyebrow">
                {data.tags.map((t) => TAG_LABELS[t] ?? t).join(' · ')}
              </span>
            </div>
          </div>

          <div className="me-count">
            <span className="me-count__n">{data.hangouts_count}</span>
            <span className="me-count__label">
              hangouts that actually happened. Only you see this.
            </span>
          </div>

          <div className="section">
            <h2 className="section__title">Settings</h2>

            <label className="switch">
              <span className="switch__text">
                <span className="row__name">Pause suggestions</span>
                <span className="row__meta">
                  We stop putting you in groups until you turn this off.
                </span>
              </span>
              <input
                type="checkbox"
                checked={data.paused}
                onChange={() => {
                  /* No endpoint yet. Agree the shape before wiring it. */
                  console.warn('pause suggestions: no endpoint yet')
                }}
              />
            </label>

            <div className="row">
              <div className="row__text">
                <span className="row__name">Your timetable</span>
                <span className="row__meta">Private. Nobody else can see it.</span>
              </div>
              <button type="button" className="btn btn--ghost">Edit</button>
            </div>

            <p className="note note--sm">
              <Icon name="lock" size={20} />
              Other students only see that you&apos;re free and the tags above.
            </p>
          </div>
        </>
      )}
    </>
  )
}
